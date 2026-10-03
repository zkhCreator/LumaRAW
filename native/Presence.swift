// Purpose: global Texture, Clarity and Dehaze controls over shared recipes.
// Inputs: slider/text actions and active recipe values. Outputs: validated partial
// edits and a scoped reset through Store. No pixels, masks, SQL or inferred values.
// The shared engine owns the processing; values use the portable -100…100 scale.
import SwiftUI

enum PresenceFields {
    static let keys=["texture","clarity","dehaze"]
}

extension Store {
    func presenceValue(_ key:String) -> Double {
        (recipe[key] as? NSNumber)?.doubleValue ?? 0
    }
    func setPresence(_ key:String,_ value:Double) {
        guard PresenceFields.keys.contains(key),value.isFinite,(-100...100).contains(value) else {
            error="Presence values must be between -100 and 100";return
        }
        set(key,value)
    }
    func resetPresence() {
        for key in PresenceFields.keys {setPresence(key,0)}
    }
}

struct PresenceControls:View {
    @EnvironmentObject var s:Store
    var body:some View {
        VStack(alignment:.leading,spacing:12) {
            ForEach(PresenceFields.keys,id:\.self) {key in
                ParameterRow(label:key.capitalized,value:Binding(get:{s.presenceValue(key)},
                    set:{s.setPresence(key,$0)}),range:-100...100,step:1)
            }
            Button("Reset Presence") {s.resetPresence()}
                .disabled(PresenceFields.keys.allSatisfy {s.presenceValue($0)==0})
        }
    }
}
