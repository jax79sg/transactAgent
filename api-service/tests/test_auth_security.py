import os
import uuid

os.environ.setdefault("DB_USER", "test")
os.environ.setdefault("DB_PASSWORD", "test")
os.environ.setdefault("JWT_SECRET", "test-secret-do-not-use-in-prod")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_ID", "test-client-id.apps.googleusercontent.com")
os.environ.setdefault("GOOGLE_OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")

import jwt
import pytest

from api_service.auth.security import decode_token, hash_password, issue_token, verify_password


class TestPasswordHashing:
    def test_correct_password_verifies(self):
        hashed = hash_password("correct horse battery staple")
        assert verify_password("correct horse battery staple", hashed) is True

    def test_wrong_password_does_not_verify(self):
        hashed = hash_password("correct horse battery staple")
        assert verify_password("wrong password", hashed) is False


class TestJwtRoundTrip:
    def test_issued_token_decodes_to_same_user_id(self):
        user_id = uuid.uuid4()
        token, expires_at = issue_token(user_id)
        decoded_user_id = decode_token(token)
        assert decoded_user_id == user_id

    def test_tampered_token_is_rejected(self):
        user_id = uuid.uuid4()
        token, _ = issue_token(user_id)
        header, payload, signature = token.rsplit(".", 2)
        # Flip a character in the *middle* of the signature, not the last one. Base64
        # packs 3 bytes into 4 characters; when the encoded length isn't a multiple of
        # 4, the trailing 1-2 characters carry some padding bits that get discarded on
        # decode -- flipping only the last character can then leave the decoded bytes
        # unchanged, so the tampered signature still verifies (confirmed flaky: ~1-in-5
        # runs, depending on the random uuid4() user_id each run happening to produce a
        # signature whose length lands on that boundary). Every character before the
        # final group encodes a full 6 bits that always maps to real output bytes, so a
        # middle-index flip always changes the decoded signature deterministically.
        mid = len(signature) // 2
        flipped_char = "A" if signature[mid] != "A" else "B"
        tampered_signature = signature[:mid] + flipped_char + signature[mid + 1 :]
        tampered = f"{header}.{payload}.{tampered_signature}"

        with pytest.raises(jwt.InvalidTokenError):
            decode_token(tampered)
