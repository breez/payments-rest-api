# Nodeless payments
Proof of concept implementation for deploying nodeless sdk as lambda function to AWS. This gives us a REST api which close to zero cost. 

Seed phrase and breez api key are stored encrypted in AWS Parameter store and decrypted when lamba accessed (a rest call is made). 

Currently implemented endpoints
- /send_payment (bolt11)
- /receive_payment (bolt11)
- /list_payments

