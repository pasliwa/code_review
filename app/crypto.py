from Crypto.Cipher import AES
from Crypto import Random
from base64 import b64encode
from base64 import b64decode


key = 'testerskeyey1234'
iv = 'testersiv1231234'

def encryption(plaintext):
    cipher = AES.new(key, AES.MODE_CFB, iv)
    return b64encode(cipher.encrypt(plaintext))

def decryption(ciphertext):
    decipher = AES.new(key, AES.MODE_CFB, iv)
    return decipher.decrypt(b64decode(ciphertext))
