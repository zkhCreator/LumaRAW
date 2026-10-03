// Purpose: local presentation preferences for the native white-balance selector.
// Inputs: a replaceable preference store and explicit toolbar changes. Outputs:
// persisted Auto Dismiss/Show Loupe/visual scale and bounded observable values.
// No catalog, recipes, engine commands, transient pointer state or pixel work.
// Defaults/range are LumaRAW choices; Adobe's guide does not publish them.
import Foundation
import SwiftUI

protocol WhiteBalancePreferenceStorage:AnyObject {
    func value(for key:String)->Any?
    func set(_ value:Any,for key:String)
}

final class UserDefaultsWhiteBalanceStorage:WhiteBalancePreferenceStorage {
    private let defaults:UserDefaults
    init(_ defaults:UserDefaults = .standard) {self.defaults=defaults}
    func value(for key:String)->Any? {defaults.object(forKey:key)}
    func set(_ value:Any,for key:String) {defaults.set(value,forKey:key)}
}

@MainActor final class WhiteBalancePreferences:ObservableObject {
    static let scaleRange=4.0...24.0
    static let defaultScale=8.0
    private let storage:WhiteBalancePreferenceStorage
    private static let prefix="WhiteBalanceSelector."
    @Published private(set) var autoDismiss:Bool
    @Published private(set) var showLoupe:Bool
    @Published private(set) var scale:Double

    init(storage:WhiteBalancePreferenceStorage? = nil) {
        let storage=storage ?? UserDefaultsWhiteBalanceStorage()
        self.storage=storage
        autoDismiss=storage.value(for:Self.prefix+"autoDismiss") as? Bool ?? true
        showLoupe=storage.value(for:Self.prefix+"showLoupe") as? Bool ?? true
        let candidate=(storage.value(for:Self.prefix+"scale") as? NSNumber)?.doubleValue
        scale=candidate.flatMap {value in
            value.isFinite && Self.scaleRange.contains(value) ? value:nil
        } ?? Self.defaultScale
    }
    func setAutoDismiss(_ value:Bool) {
        guard value != autoDismiss else {return}
        storage.set(value,for:Self.prefix+"autoDismiss");autoDismiss=value
    }
    func setShowLoupe(_ value:Bool) {
        guard value != showLoupe else {return}
        storage.set(value,for:Self.prefix+"showLoupe");showLoupe=value
    }
    func setScale(_ value:Double) {
        guard value.isFinite else {return}
        let value=min(Self.scaleRange.upperBound,max(Self.scaleRange.lowerBound,value))
        guard value != scale else {return}
        storage.set(value,for:Self.prefix+"scale");scale=value
    }
}
