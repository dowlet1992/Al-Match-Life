import Foundation
import Security

public enum SecureTokenStoreError: Error, Sendable {
    case keychain(OSStatus)
    case invalidTokenData
}

public protocol SecureTokenStoring: Sendable {
    func save(_ token: String, account: String) throws
    func read(account: String) throws -> String?
    func delete(account: String) throws
}

public struct KeychainTokenStore: SecureTokenStoring, Sendable {
    private let service: String

    public init(service: String = "com.aimatchlife.mobile.auth") {
        self.service = service
    }

    public func save(_ token: String, account: String) throws {
        guard let data = token.data(using: .utf8), !data.isEmpty else {
            throw SecureTokenStoreError.invalidTokenData
        }
        let identity: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let updateStatus = SecItemUpdate(
            identity as CFDictionary,
            [kSecValueData as String: data] as CFDictionary
        )
        if updateStatus == errSecSuccess { return }
        guard updateStatus == errSecItemNotFound else {
            throw SecureTokenStoreError.keychain(updateStatus)
        }
        let query: [String: Any] = identity.merging([
            kSecAttrAccessible as String: kSecAttrAccessibleWhenUnlockedThisDeviceOnly,
            kSecValueData as String: data,
        ]) { _, new in new }
        let status = SecItemAdd(query as CFDictionary, nil)
        guard status == errSecSuccess else { throw SecureTokenStoreError.keychain(status) }
    }

    public func read(account: String) throws -> String? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess else { throw SecureTokenStoreError.keychain(status) }
        guard let data = result as? Data, let token = String(data: data, encoding: .utf8) else {
            throw SecureTokenStoreError.invalidTokenData
        }
        return token
    }

    public func delete(account: String) throws {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        let status = SecItemDelete(query as CFDictionary)
        guard status == errSecSuccess || status == errSecItemNotFound else {
            throw SecureTokenStoreError.keychain(status)
        }
    }
}
