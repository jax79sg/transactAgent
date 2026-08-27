#!/usr/bin/env bash
# Creates a login for the Kubernetes deployment, the same way README.md's "Create
# your login" section does for docker-compose: the password is hashed INSIDE the
# api-service pod using the app's own real hashing code (api_service.auth.security),
# not a separately-installed bcrypt copy, avoiding any version-mismatch risk.
#
# Improves on the docker-compose one-liner in one way: username/password are piped
# over stdin via a heredoc, never passed as a `kubectl exec` command-line argument --
# so neither ever appears in the Kubernetes API server's audit log/event history,
# `kubectl` process listings, or this machine's shell history. Nothing is echoed to
# the terminal or written to a file at any point.
#
# Usage: ./create-k8s-user.sh
# (Prompts interactively for username, password, and password confirmation.)

set -euo pipefail

NAMESPACE="${K8S_NAMESPACE:-transactagent}"
DEPLOYMENT="${K8S_API_DEPLOYMENT:-deploy/api-service}"

if ! command -v kubectl >/dev/null 2>&1; then
  echo "Error: the 'kubectl' CLI is not installed or not on PATH." >&2
  exit 1
fi

if ! kubectl -n "$NAMESPACE" get "$DEPLOYMENT" >/dev/null 2>&1; then
  echo "Error: $DEPLOYMENT not found in namespace $NAMESPACE." >&2
  echo "(Set K8S_NAMESPACE/K8S_API_DEPLOYMENT if yours differ from the defaults.)" >&2
  exit 1
fi

echo "Create a login for the Kubernetes deployment (namespace: $NAMESPACE)."
echo

read -r -p "Username: " USERNAME
if [ -z "$USERNAME" ]; then
  echo "Error: username must not be empty." >&2
  exit 1
fi

read -r -s -p "Password: " PASSWORD
echo
read -r -s -p "Confirm password: " PASSWORD_CONFIRM
echo

if [ -z "$PASSWORD" ]; then
  echo "Error: password must not be empty." >&2
  exit 1
fi

if [ "$PASSWORD" != "$PASSWORD_CONFIRM" ]; then
  echo "Error: passwords do not match." >&2
  exit 1
fi

# Reads username/password from stdin (2 lines) rather than embedding them in the
# script text itself -- keeps them out of this string entirely, so there's nothing
# secret in the `python3 -c` argument, only executable code.
PY_SCRIPT='
import sys

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from transactagent_db.migrate import build_database_url
from transactagent_db.models import User
from api_service.auth.security import hash_password

username = sys.stdin.readline().rstrip("\n")
password = sys.stdin.readline().rstrip("\n")

if not username or not password:
    print("Error: username and password must not be empty.", file=sys.stderr)
    sys.exit(1)

engine = create_engine(build_database_url())
with Session(engine) as session:
    session.add(User(username=username, password_hash=hash_password(password)))
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        print(f"Error: a user named {username!r} already exists.", file=sys.stderr)
        sys.exit(1)

print(f"User {username!r} created.")
'

kubectl -n "$NAMESPACE" exec -i "$DEPLOYMENT" -- python3 -c "$PY_SCRIPT" <<EOF
$USERNAME
$PASSWORD
EOF

unset PASSWORD PASSWORD_CONFIRM
