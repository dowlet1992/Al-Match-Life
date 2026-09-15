# NOVIX external release checklist

Everything below requires an external account, public infrastructure, or real device. Local application work is complete independently of these items.

## Public web release

- Buy or connect the production domain.
- Provision a Linux server with Docker and persistent backups.
- Point DNS to the server.
- Issue a Let's Encrypt certificate and enable `deploy/docker-compose.tls.yml`.
- Store production secrets outside Git and rotate any credentials previously used during development.
- Configure production LiveKit with a public WebSocket URL and TURN/TLS connectivity.

## Mobile delivery

- Create a Firebase project and provide FCM credentials for Android push notifications.
- Enrol in Apple Developer Program and provide APNs credentials for iOS push notifications.
- Build signed Android and iOS clients and test calls, media uploads, notifications, and background delivery on real devices.

## Final acceptance

- Run the security audit against the public HTTPS domain.
- Run a production-like load test with monitoring enabled.
- Verify backups and perform one restore drill.
- Complete privacy policy, terms, data-retention policy, and store compliance forms for the launch countries.
