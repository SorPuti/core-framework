"""
Implementações de hashers de senha.

Hashers disponíveis:
- PBKDF2Hasher: Padrão, sem dependências extras
- Argon2Hasher: Mais seguro, requer argon2-cffi
- BCryptHasher: Popular, requer bcrypt
- ScryptHasher: Alternativa, sem dependências extras

Uso:
    from core.auth import get_password_hasher, register_password_hasher
    
    # Usar hasher padrão
    hasher = get_password_hasher()
    hashed = hasher.hash("password123")
    
    # Verificar
    if hasher.verify("password123", hashed):
        print("Senha correta!")
    
    # Registrar hasher customizado
    class MyHasher(PasswordHasher):
        algorithm = "my_algo"
        ...
    
    register_password_hasher("my_algo", MyHasher())
"""

from __future__ import annotations

import hashlib
import secrets
import base64
from typing import Any

from core.auth.base import PasswordHasher, register_password_hasher


class PBKDF2Hasher(PasswordHasher):
    """
    Hasher usando PBKDF2 com SHA256.
    
    Padrão do framework - não requer dependências extras.
    
    Formato do hash: pbkdf2_sha256$iterations$salt$hash
    """
    
    algorithm = "pbkdf2_sha256"
    iterations = 600_000  # OWASP 2023 recommendation
    digest = hashlib.sha256
    
    def __init__(self, iterations: int | None = None) -> None:
        if iterations is not None:
            self.iterations = iterations
    
    def hash(self, password: str) -> str:
        salt = secrets.token_hex(16)
        hash_value = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            self.iterations,
        )
        hash_b64 = base64.b64encode(hash_value).decode("ascii")
        return f"{self.algorithm}${self.iterations}${salt}${hash_b64}"
    
    def verify(self, password: str, hashed: str) -> bool:
        try:
            parts = hashed.split("$")
            if len(parts) != 4:
                return False
            
            algorithm, iterations_str, salt, stored_hash = parts
            
            if algorithm != self.algorithm:
                return False
            
            iterations = int(iterations_str)
            
            new_hash = hashlib.pbkdf2_hmac(
                "sha256",
                password.encode("utf-8"),
                salt.encode("utf-8"),
                iterations,
            )
            new_hash_b64 = base64.b64encode(new_hash).decode("ascii")
            
            return secrets.compare_digest(stored_hash, new_hash_b64)
        except (ValueError, AttributeError):
            return False
    
    def needs_rehash(self, hashed: str) -> bool:
        """Verifica se precisa recalcular (iterações antigas)."""
        try:
            parts = hashed.split("$")
            if len(parts) != 4:
                return True
            
            _, iterations_str, _, _ = parts
            stored_iterations = int(iterations_str)
            
            # Rehash se iterações menores que o atual
            return stored_iterations < self.iterations
        except (ValueError, IndexError):
            return True


class Argon2Hasher(PasswordHasher):
    """
    Hasher usando Argon2id (recomendado para novas aplicações).
    
    Requer: pip install argon2-cffi
    
    Argon2 é o vencedor do Password Hashing Competition e é
    considerado o algoritmo mais seguro atualmente.
    """
    
    algorithm = "argon2"
    
    # Parâmetros Argon2 (OWASP recommendations)
    time_cost = 3  # Iterações
    memory_cost = 65536  # 64 MB
    parallelism = 4
    hash_len = 32
    salt_len = 16
    
    def __init__(
        self,
        time_cost: int | None = None,
        memory_cost: int | None = None,
        parallelism: int | None = None,
    ) -> None:
        if time_cost is not None:
            self.time_cost = time_cost
        if memory_cost is not None:
            self.memory_cost = memory_cost
        if parallelism is not None:
            self.parallelism = parallelism
    
    def _get_hasher(self) -> Any:
        try:
            from argon2 import PasswordHasher as Argon2PH
            return Argon2PH(
                time_cost=self.time_cost,
                memory_cost=self.memory_cost,
                parallelism=self.parallelism,
                hash_len=self.hash_len,
                salt_len=self.salt_len,
            )
        except ImportError:
            raise ImportError(
                "argon2-cffi is required for Argon2Hasher. "
                "Install with: pip install argon2-cffi"
            )
    
    def hash(self, password: str) -> str:
        ph = self._get_hasher()
        return ph.hash(password)
    
    def verify(self, password: str, hashed: str) -> bool:
        try:
            from argon2.exceptions import VerifyMismatchError, InvalidHashError
            ph = self._get_hasher()
            ph.verify(hashed, password)
            return True
        except (VerifyMismatchError, InvalidHashError):
            return False
        except ImportError:
            return False
    
    def needs_rehash(self, hashed: str) -> bool:
        try:
            ph = self._get_hasher()
            return ph.check_needs_rehash(hashed)
        except (ImportError, Exception):
            return True


class BCryptHasher(PasswordHasher):
    """
    Hasher usando BCrypt.
    
    Requer: pip install bcrypt
    
    BCrypt é um algoritmo popular e bem testado.
    """
    
    algorithm = "bcrypt"
    rounds = 12  # Cost factor (2^12 = 4096 iterations)
    
    def __init__(self, rounds: int | None = None) -> None:
        if rounds is not None:
            self.rounds = rounds
    
    def hash(self, password: str) -> str:
        try:
            import bcrypt
            salt = bcrypt.gensalt(rounds=self.rounds)
            hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
            return f"{self.algorithm}${hashed.decode('utf-8')}"
        except ImportError:
            raise ImportError(
                "bcrypt is required for BCryptHasher. "
                "Install with: pip install bcrypt"
            )
    
    def verify(self, password: str, hashed: str) -> bool:
        try:
            import bcrypt
            
            # Remove prefixo do algoritmo se presente
            if hashed.startswith(f"{self.algorithm}$"):
                hashed = hashed[len(self.algorithm) + 1:]
            
            return bcrypt.checkpw(
                password.encode("utf-8"),
                hashed.encode("utf-8"),
            )
        except (ImportError, ValueError):
            return False
    
    def needs_rehash(self, hashed: str) -> bool:
        """BCrypt não tem método nativo de verificação de rehash."""
        return False


class ScryptHasher(PasswordHasher):
    """
    Hasher usando Scrypt.
    
    Não requer dependências extras (usa hashlib).
    
    Scrypt é memory-hard, tornando ataques de GPU mais difíceis.
    """
    
    algorithm = "scrypt"
    
    # Parâmetros Scrypt
    n = 2**14  # CPU/memory cost (16384)
    r = 8  # Block size
    p = 1  # Parallelization
    dklen = 64  # Derived key length
    
    def __init__(
        self,
        n: int | None = None,
        r: int | None = None,
        p: int | None = None,
    ) -> None:
        if n is not None:
            self.n = n
        if r is not None:
            self.r = r
        if p is not None:
            self.p = p
    
    def hash(self, password: str) -> str:
        salt = secrets.token_bytes(16)
        
        derived = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=self.n,
            r=self.r,
            p=self.p,
            dklen=self.dklen,
        )
        
        salt_b64 = base64.b64encode(salt).decode("ascii")
        hash_b64 = base64.b64encode(derived).decode("ascii")
        
        return f"{self.algorithm}${self.n}${self.r}${self.p}${salt_b64}${hash_b64}"
    
    def verify(self, password: str, hashed: str) -> bool:
        try:
            parts = hashed.split("$")
            if len(parts) != 6:
                return False
            
            algorithm, n_str, r_str, p_str, salt_b64, stored_hash = parts
            
            if algorithm != self.algorithm:
                return False
            
            n = int(n_str)
            r = int(r_str)
            p = int(p_str)
            salt = base64.b64decode(salt_b64)
            
            derived = hashlib.scrypt(
                password.encode("utf-8"),
                salt=salt,
                n=n,
                r=r,
                p=p,
                dklen=self.dklen,
            )
            
            new_hash_b64 = base64.b64encode(derived).decode("ascii")
            
            return secrets.compare_digest(stored_hash, new_hash_b64)
        except (ValueError, AttributeError):
            return False
    
    def needs_rehash(self, hashed: str) -> bool:
        """Verifica se parâmetros são menores que os atuais."""
        try:
            parts = hashed.split("$")
            if len(parts) != 6:
                return True
            
            _, n_str, r_str, p_str, _, _ = parts
            stored_n = int(n_str)
            
            return stored_n < self.n
        except (ValueError, IndexError):
            return True


# =============================================================================
# Hasher Multi-Algoritmo (para migração)
# =============================================================================

class MultiHasher(PasswordHasher):
    """
    Hasher que suporta múltiplos algoritmos.
    
    Útil para migração gradual de algoritmos:
    
        hasher = MultiHasher(
            preferred="argon2",
            fallbacks=["pbkdf2_sha256", "bcrypt"],
        )
        
        # Novos hashes usam argon2
        hashed = hasher.hash("password")
        
        # Verifica com qualquer algoritmo
        hasher.verify("password", old_pbkdf2_hash)  # True
        hasher.verify("password", old_bcrypt_hash)  # True
    """
    
    algorithm = "multi"
    
    def __init__(
        self,
        preferred: str = "pbkdf2_sha256",
        fallbacks: list[str] | None = None,
    ) -> None:
        self.preferred = preferred
        self.fallbacks = fallbacks or []
        self._hashers: dict[str, PasswordHasher] = {}
    
    def _get_hasher(self, algorithm: str) -> PasswordHasher:
        if algorithm not in self._hashers:
            from core.auth.base import get_password_hasher
            self._hashers[algorithm] = get_password_hasher(algorithm)
        return self._hashers[algorithm]
    
    def hash(self, password: str) -> str:
        """Usa o hasher preferido para novos hashes."""
        hasher = self._get_hasher(self.preferred)
        return hasher.hash(password)
    
    def verify(self, password: str, hashed: str) -> bool:
        """Tenta verificar com todos os hashers."""
        # Detecta algoritmo do hash
        algorithm = self.get_algorithm_from_hash(hashed)
        
        if algorithm:
            try:
                hasher = self._get_hasher(algorithm)
                return hasher.verify(password, hashed)
            except KeyError:
                pass
        
        # Tenta todos os hashers
        all_algorithms = [self.preferred] + self.fallbacks
        for algo in all_algorithms:
            try:
                hasher = self._get_hasher(algo)
                if hasher.verify(password, hashed):
                    return True
            except KeyError:
                continue
        
        return False
    
    def needs_rehash(self, hashed: str) -> bool:
        """Verifica se deve migrar para o algoritmo preferido."""
        algorithm = self.get_algorithm_from_hash(hashed)
        
        if algorithm != self.preferred:
            return True
        
        try:
            hasher = self._get_hasher(algorithm)
            return hasher.needs_rehash(hashed)
        except KeyError:
            return True


# =============================================================================
# Registro dos hashers padrão
# =============================================================================

def _register_default_hashers() -> None:
    """Registra os hashers padrão."""
    register_password_hasher("pbkdf2_sha256", PBKDF2Hasher())
    register_password_hasher("pbkdf2", PBKDF2Hasher())  # Alias
    register_password_hasher("scrypt", ScryptHasher())
    
    # Hashers que requerem dependências opcionais
    # São registrados mas podem falhar ao usar se não instalados
    register_password_hasher("argon2", Argon2Hasher())
    register_password_hasher("bcrypt", BCryptHasher())


# Registra ao importar
_register_default_hashers()
