// Purpose: isolated local preference storage for native selector regressions.
// Inputs: test option changes. Outputs: in-memory persistence assertions only.
// Never reads or changes user defaults, catalogs or engine state.
import Foundation

final class MemoryWhiteBalancePreferences:WhiteBalancePreferenceStorage {
    var values:[String:Any]=[:]
    func value(for key:String)->Any? {values[key]}
    func set(_ value:Any,for key:String) {values[key]=value}
}
