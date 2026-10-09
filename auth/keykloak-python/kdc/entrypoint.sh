#!/bin/sh
set -e

# First start only: create the realm, users and Keycloak's service principal.
if [ ! -f /var/lib/krb5kdc/principal ]; then
  kdb5_util create -s -r LAB.LOCAL -P masterpw
  kadmin.local -q "addprinc -pw alice123 alice"
  kadmin.local -q "addprinc -randkey HTTP/keycloak.lab.local"
fi

# Keycloak reads this keytab to validate SPNEGO tickets.
# ponytail: re-exported each start (-norandkey keeps the key stable), keeps the shared volume in sync
rm -f /keytabs/keycloak.keytab
kadmin.local -q "ktadd -norandkey -k /keytabs/keycloak.keytab HTTP/keycloak.lab.local"
chmod 644 /keytabs/keycloak.keytab

exec krb5kdc -n -r LAB.LOCAL
