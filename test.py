from email_service import send_verification_email

print("Starting email test...")
test_email = "nexusjuan@gmail.com"
test_token = "test-token-123"

result = send_verification_email(test_email, test_token)
print(f"Test result: {'Success' if result else 'Failed'}")
