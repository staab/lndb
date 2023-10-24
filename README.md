# Marketing page

- End-to-end Encryption - use our javascript SDK to get access to full client-side encryption.
- Multi-tenancy - Create unlimited child accounts to isolate end-user data.
- Powered by Lightning - Pay by the micro-sat with our integrated bitcoin/lightning wallet
- Integrated social graph - Take advantage of Nostr's interoperable social protocol to expand your reach
- Low-level access - Run remote queries against encrypted and sandboxed sqlite instances
- Easy and Powerful - Our higher-level APIs are powered by best-in class database technology
- Run a node - Skip the fees and strengthen the network by running your own Motive relay

Integrate redis and postgres? Add a job queue? Static hosting?

The social protocol could be the killer feature. Use cases:

- In-app social primitives for free
- Post media for an application to a wider network
- Cross-app DMs and payments
- Standard content schema allows for pulling content from a wider network

# Multi-tenancy

Create a new key with scope limited to child account creation, then create a child account for each user. To create a read-only database, create a separate account then create a new key with read-only scopes.

Make it possible to pass server costs along to users by making them pay invoices directly into the app developer's server account, then allow them to request payouts. Although would this mean I'm doing business directly with end users, and so it's all my responsibility?

- [ ] Sqlite security https://www.sqlite.org/security.html
- [ ] Accept ToS via endpoint
- [ ] File storage
- [ ] K/v store
- [ ] Bespoke database
- [ ] Integrations - allow users to create a credential, then specify the credential by name from child account to keep the token private? Paywall it?
  - Email/text
