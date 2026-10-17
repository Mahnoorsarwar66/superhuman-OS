# Connector references checked during preparation

Implementation uses native read-only APIs and the app's existing mail connector, not ChatGPT connector sessions. Current account permissions, administrator policies and provider availability must still be verified on connection.

- Slack history: https://docs.slack.dev/reference/methods/conversations.history/
- Slack threads and token constraints: https://docs.slack.dev/reference/methods/conversations.replies/
- Slack authentication identity: https://docs.slack.dev/reference/methods/auth.test/
- Slack rate limits: https://docs.slack.dev/apis/web-api/rate-limits/
- Google installed-app OAuth and PKCE: https://developers.google.com/identity/protocols/oauth2/native-app
- Google token expiration: https://developers.google.com/identity/protocols/oauth2#expiration
- Meta WhatsApp setup: https://developers.facebook.com/documentation/business-messaging/whatsapp/get-started.md/
- Meta webhook setup: https://developers.facebook.com/documentation/business-messaging/whatsapp/webhooks/create-webhook-endpoint.md/
- Meta webhook payload: https://developers.facebook.com/documentation/business-messaging/whatsapp/reference/webhooks/whatsapp-incoming-webhook-payload/
- Meta maintained webhook signature example: https://github.com/fbsamples/whatsapp-api-examples/blob/main/signature-validation-with-webhooks-payloads/app.py

Some Meta documentation pages were rate-limited during retrieval; indexed official pages and Meta's maintained sample were also consulted. No live Meta account or Slack workspace was used. OAuth/Webhook account configuration must follow the provider's current requirements. This read/draft release does not implement outbound messaging or rely on assumed per-message sending prices.
