import UIKit
import Social
import MobileCoreServices

/**
 * ShareViewController.swift
 *
 * Task 4 — iOS Share Extension.
 * Appears in the native iOS Share Sheet when the user taps Share on any
 * URL in YouTube, Instagram, TikTok, Safari, etc.
 *
 * When activated:
 *   1. Extracts the shared URL from the extension context
 *   2. Opens the ReelRoutes app via deep link: reelroutes://import?url=<encoded_url>
 *   3. The Expo app handles the deep link in new-trip.tsx via expo-linking
 *
 * Installation:
 *   1. Add this file to ios/ShareExtension/ShareViewController.swift
 *   2. Add the ShareExtension target in Xcode (File > New > Target > Share Extension)
 *   3. Set the bundle ID to: app.reelroutes.mobile.ShareExtension
 *   4. Add the App Group entitlement: group.app.reelroutes.mobile
 *   5. Enable App Groups in both the main target and this extension target
 */
class ShareViewController: SLComposeServiceViewController {

    override func isContentValid() -> Bool {
        return true
    }

    override func didSelectPost() {
        guard let items = extensionContext?.inputItems as? [NSExtensionItem] else {
            finish()
            return
        }

        for item in items {
            guard let attachments = item.attachments else { continue }
            for provider in attachments {
                // Handle URL type
                if provider.hasItemConformingToTypeIdentifier(kUTTypeURL as String) {
                    provider.loadItem(forTypeIdentifier: kUTTypeURL as String) { [weak self] url, error in
                        if let url = url as? URL {
                            self?.openMainApp(with: url.absoluteString)
                        } else if let url = url as? String {
                            self?.openMainApp(with: url)
                        }
                    }
                    return
                }
                // Handle plain text (some apps share URLs as text)
                if provider.hasItemConformingToTypeIdentifier(kUTTypePlainText as String) {
                    provider.loadItem(forTypeIdentifier: kUTTypePlainText as String) { [weak self] text, error in
                        if let text = text as? String,
                           let url = URL(string: text.trimmingCharacters(in: .whitespacesAndNewlines)),
                           url.scheme == "https" || url.scheme == "http" {
                            self?.openMainApp(with: text.trimmingCharacters(in: .whitespacesAndNewlines))
                        }
                    }
                    return
                }
            }
        }
        finish()
    }

    private func openMainApp(with urlString: String) {
        guard let encoded = urlString.addingPercentEncoding(withAllowedCharacters: .urlQueryAllowed),
              let deepLink = URL(string: "reelroutes://import?url=\(encoded)") else {
            finish()
            return
        }

        // Open the main ReelRoutes app
        var responder: UIResponder? = self
        while responder != nil {
            if let application = responder as? UIApplication {
                application.open(deepLink, options: [:], completionHandler: nil)
                break
            }
            responder = responder?.next
        }
        finish()
    }

    private func finish() {
        extensionContext?.completeRequest(returningItems: [], completionHandler: nil)
    }

    override func configurationItems() -> [Any]! {
        return []
    }
}
