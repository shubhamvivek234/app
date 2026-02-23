import time
from passlib.context import CryptContext
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
start = time.time()
hash_val = pwd_context.hash("wrongpassword")
print(f"Hash time: {time.time() - start:.4f}s")
start = time.time()
pwd_context.verify("wrongpassword", hash_val)
print(f"Verify time: {time.time() - start:.4f}s")
