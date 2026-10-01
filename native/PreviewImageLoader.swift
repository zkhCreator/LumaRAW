// Purpose: prepare immutable service preview images without blocking the UI.
// Inputs: local image paths emitted by the engine. Outputs: decoded ICC-bearing
// NSImages, or nil for missing/invalid/oversized files. Two background operations
// bound simultaneous decode work. Native code does no grading or color transform;
// ImageIO decodes the engine's finished PNG/JPEG with its original color space.
import AppKit
import ImageIO

enum PreviewImageLoader {
    private static let queue:OperationQueue = {
        let queue=OperationQueue();queue.name="local.lumaraw.preview-image-load"
        queue.maxConcurrentOperationCount=2;queue.qualityOfService = .userInitiated
        return queue
    }()
    static func load(_ path:String?) async -> NSImage? {
        guard let path,!Task.isCancelled else {return nil}
        return await withCheckedContinuation {continuation in
            queue.addOperation {
                let image=autoreleasepool {()->NSImage? in
                    guard let attrs=try? FileManager.default.attributesOfItem(atPath:path),
                          attrs[.type] as? FileAttributeType == .typeRegular,
                          let size=attrs[.size] as? NSNumber,size.intValue<=32*1024*1024,
                          let source=CGImageSourceCreateWithURL(URL(fileURLWithPath:path) as CFURL,nil),
                          let properties=CGImageSourceCopyPropertiesAtIndex(source,0,nil) as? [CFString:Any],
                          let width=properties[kCGImagePropertyPixelWidth] as? Int,
                          let height=properties[kCGImagePropertyPixelHeight] as? Int,
                          width>0,height>0,height<=16_777_216,width<=16_777_216/height,
                          let image=CGImageSourceCreateImageAtIndex(source,0,
                            [kCGImageSourceShouldCache:true,kCGImageSourceShouldCacheImmediately:true] as CFDictionary) else {return nil}
                    // NSCGImageSnapshotRep can report 2x pixels on Retina when
                    // NSImage(cgImage:size:) is used. Preserve the actual raster
                    // dimensions with an explicit bitmap representation.
                    let representation=NSBitmapImageRep(cgImage:image)
                    let prepared=NSImage(size:NSSize(width:image.width,height:image.height))
                    prepared.addRepresentation(representation)
                    return prepared
                }
                continuation.resume(returning:image)
            }
        }
    }
}
