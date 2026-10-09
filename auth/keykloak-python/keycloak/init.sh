#!/bin/bash
# Realm settings that a realm import can't set. Safe to run repeatedly.
set -e
KCADM="/opt/keycloak/bin/kcadm.sh"
CFG="--config /tmp/kcadm.config"

until $KCADM config credentials $CFG --server http://keycloak.lab.local:8080 --realm master --user admin --password admin; do
  echo "waiting for keycloak..."; sleep 3
done
until $KCADM get realms/lab $CFG --fields realm >/dev/null 2>&1; do
  echo "waiting for realm import..."; sleep 3
done

# 1. Import leaves the "Kerberos" (auth-spnego) step of the browser flow DISABLED.
#    Turn it on so Keycloak answers with "WWW-Authenticate: Negotiate".
id=$($KCADM get authentication/flows/browser/executions -r lab $CFG --fields id,providerId --format csv --noquotes \
  | grep ',auth-spnego$' | cut -d, -f1)
$KCADM update authentication/flows/browser/executions -r lab $CFG -b "{\"id\":\"$id\",\"requirement\":\"ALTERNATIVE\"}"
echo "Kerberos (SPNEGO) step in browser flow set to ALTERNATIVE"

# 2. Kerberos gives Keycloak only a username (no first/last name), and the default user profile
#    requires them, so the first login would stop at an "update profile" form.
# ponytail: disables the check realm-wide; make firstName/lastName optional in the user profile if you want it back
$KCADM update authentication/required-actions/VERIFY_PROFILE -r lab $CFG -s enabled=false
echo "VERIFY_PROFILE required action disabled"

# 3. Self-registration: the "Register" link on the login page (keycloak.register() in the SPA).
#    Registered accounts live in Keycloak's own DB. Keycloak's Kerberos connector is read-only,
#    so they are password users, not Kerberos principals.
#    loginWithEmailAllowed MUST stay false: with it on, sign-up also looks the email up as a username, and the
#    Kerberos provider reads "dana@example.com" as principal dana@EXAMPLE.COM -> no KDC for that realm ->
#    "Kerberos unreachable" -> every registration fails. Users log in with their username instead.
$KCADM update realms/lab $CFG -s registrationAllowed=true -s loginWithEmailAllowed=false -s duplicateEmailsAllowed=false
echo "Self-registration enabled (login by username)"
