"""Use the user's OS credential vault instead of plaintext application settings."""
SERVICE='NeuroWings'
ACCOUNT='GPT API key'
def read_key():
    import keyring
    return keyring.get_password(SERVICE,ACCOUNT) or ''
def write_key(value):
    import keyring
    if value:
        keyring.set_password(SERVICE,ACCOUNT,value)
    else:
        try:keyring.delete_password(SERVICE,ACCOUNT)
        except keyring.errors.PasswordDeleteError:pass
