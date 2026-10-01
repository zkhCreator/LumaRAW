// Purpose: reuse one bounded native-to-engine stdio relay instead of launching
// a fresh engine for every control, poll or preview request. Inputs: commands.
// Outputs: correlated service envelopes on background queues. No UI, SQL, image
// work or mutation replay. Failed streams fail every pending call with an unknown
// outcome; only a subsequent new caller can launch a replacement relay.
import Foundation

// All mutable transport state is confined to queue; reader callbacks re-enter it.
final class NativeCommandTransport:@unchecked Sendable {
    private let queue=DispatchQueue(label:"local.lumaraw.native-command-transport",qos:.userInitiated)
    private let executable:String,catalog:String
    private var process:Process?
    private var input:FileHandle?
    private var buffer=Data()
    private var pending:[Int:CheckedContinuation<[String:Any],Error>]=[:]
    private var controlIDs:Set<Int>=[]
    private var deadlines:[Int:Date]=[:]
    private var watchdog:DispatchSourceTimer?
    private var nextID=0
    private var generation=0
    private let maximum=1024*1024

    init(executable:String,catalog:String) {self.executable=executable;self.catalog=catalog}

    func call(_ method:String,_ params:[String:Any]) async throws -> [String:Any] {
        try await withCheckedThrowingContinuation {continuation in
            queue.async {
                let control=method=="cancel_preview" || method=="service_connection"
                guard control ? self.controlIDs.count<8:self.pending.count-self.controlIDs.count<32 else {
                    continuation.resume(throwing:EngineFailure(message:"Too many outstanding service commands. This command was not sent."));return
                }
                do {
                    self.nextID+=1;let id=self.nextID
                    let payload=try JSONSerialization.data(withJSONObject:["id":id,"method":method,"params":params])+Data([10])
                    guard payload.count<=self.maximum else {
                        throw EngineFailure(message:"The service command is too large. This command was not sent.")
                    }
                    if self.process==nil {try self.start()}
                    self.pending[id]=continuation
                    if control {self.controlIDs.insert(id)}
                    self.deadlines[id]=Date().addingTimeInterval(650)
                    if self.watchdog==nil {
                        let timer=DispatchSource.makeTimerSource(queue:self.queue)
                        timer.schedule(deadline:.now()+10,repeating:10)
                        timer.setEventHandler { [weak self] in
                            guard let self,self.deadlines.values.contains(where:{$0<=Date()}) else {return}
                            self.failStream("The service connection timed out.")
                        }
                        self.watchdog=timer;timer.resume()
                    }
                    do {try self.input!.write(contentsOf:payload)}
                    catch {self.failStream("The service connection failed while sending a command.")}
                } catch {continuation.resume(throwing:error)}
            }
        }
    }

    private func start() throws {
        let process=Process(),stdin=Pipe(),stdout=Pipe()
        process.executableURL=URL(fileURLWithPath:executable)
        process.arguments=["--catalog",catalog,"--native-client"]
        process.standardInput=stdin;process.standardOutput=stdout;process.standardError=FileHandle.nullDevice
        try process.run()
        generation+=1;let token=generation
        self.process=process;input=stdin.fileHandleForWriting;buffer=Data()
        DispatchQueue.global(qos:.userInitiated).async { [weak self] in
            while true {
                // read(upToCount:) waits to fill its length on macOS pipes.
                // availableData returns the bytes currently ready for framing.
                let chunk=stdout.fileHandleForReading.availableData
                if chunk.isEmpty {break}
                self?.queue.async { [weak self] in
                    guard let self,self.generation==token else {return}
                    self.receive(chunk)
                }
            }
            try? stdout.fileHandleForReading.close()
            self?.queue.async { [weak self] in
                guard let self,self.generation==token else {return}
                self.failStream("The service connection closed before completing its replies.")
            }
            process.waitUntilExit()
        }
    }

    private func receive(_ data:Data) {
        buffer.append(data)
        while let newline=buffer.firstIndex(of:10) {
            let length=buffer.distance(from:buffer.startIndex,to:newline)
            guard length<=maximum else {failStream("The service response exceeded its limit.");return}
            let line=Data(buffer.prefix(length));buffer.removeFirst(length+1)
            do {
                guard let envelope=try JSONSerialization.jsonObject(with:line) as? [String:Any],
                      let id=envelope["id"] as? Int,let continuation=pending.removeValue(forKey:id) else {
                    failStream("The service returned an unrecognized response.");return
                }
                controlIDs.remove(id)
                deadlines.removeValue(forKey:id)
                if pending.isEmpty {watchdog?.cancel();watchdog=nil}
                if envelope["ok"] as? Bool==true,let result=envelope["result"] as? [String:Any] {
                    continuation.resume(returning:result)
                } else {
                    continuation.resume(throwing:EngineFailure(message:envelope["error"] as? String ?? "The service request failed",
                        canActivateService:envelope["can_activate"] as? Bool ?? false))
                }
            } catch {failStream("The service returned invalid JSON.");return}
        }
        if buffer.count>maximum {failStream("The service response exceeded its limit.")}
    }

    private func failStream(_ message:String) {
        generation+=1
        try? input?.close();input=nil
        // Closing stdin asks the relay to drain admitted calls. Never terminate
        // a relay just to make a possibly committed mutation look cancelled.
        process=nil;buffer=Data()
        let calls=pending.values;pending=[:];controlIDs=[];deadlines=[:]
        watchdog?.cancel();watchdog=nil
        let error=EngineFailure(message:message+" A submitted action may have completed. Refresh its state before retrying.")
        for continuation in calls {continuation.resume(throwing:error)}
    }
}
