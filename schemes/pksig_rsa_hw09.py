"""
Hohenberger-Waters Stateful Signatures (RSA-based)
 
 | From: "S. Hohenberger, B. Waters. Realizing Hash-and-Sign Signatures under Standard Assumptions", Section 3.
 | Published in: Eurocrypt 2009
 | Available from: http://eprint.iacr.org/2009/028.pdf
 | Notes: 

 * type:       signature (public key)
 * setting:      RSA
 * assumption:   RSA

:Author:    J Ayo Akinyele/Christina Garman
:Date:      12/2011
:Status:    Needs Improvement.
"""

from charm.integer import *
from toolbox.PKSig import PKSig
from chamhash_rsa_hw09 import ChamHash_HW09
from toolbox.conversion import Conversion
from toolbox.bitstring import Bytes
from toolbox.specialprimes import BlumWilliamsInteger
import hmac, hashlib, math

debug = False

def SHA1(bytes1):
  s1 = hashlib.new('sha1')
  s1.update(bytes1)
  return s1.digest()


def randomQR(n):
    return random(n) ** 2
    
class LogFunction:
  def __init__(self, base=10):
    self.base = base
  
  def __getitem__(self, base):
    return LogFunction(base)
  
  def __call__(self, val):
    return math.log(val, self.base)
log = LogFunction()

class Prf:
  def __init__(self):
      pass
  
  @classmethod
  def keygen(self, bits):
    return integer(randomBits(bits))

  @classmethod  
  def eval(self, k, input1): 
    if type(k) == integer:
        h = hmac.new(serialize(k), b'', hashlib.sha1)
    else:
        h = hmac.new(serialize(integer(k)), b'', hashlib.sha1)
    
    h.update(input1)
    return Conversion.bytes2integer(h.hexdigest())

class BlumIntegerSquareRoot:
  def __init__(self, p, q):
    self.raisedToThePower = 1
    self.p = p
    self.q = q
    
  def pow(self, modularInt):
    p, q = self.p, self.q
    result = integer(modularInt) % (p * q)
    for repeat in range(self.raisedToThePower):
        result = result ** (((p-1)*(q-1)+4)/8)
    return result

  def __pow__(self, power):
    exp = BlumIntegerSquareRoot(self.p, self.q)
    exp.raisedToThePower = power
    return exp.pow(power)

class Sig_RSA_Stateless_HW09(PKSig):
    def __init__(self, CH = ChamHash_HW09):
        self.BWInt = BlumWilliamsInteger()
        self.Prf = Prf()
        self.ChameleonHash = CH()
        
    def keygen(self, keyLength=1024):
        # Generate a Blum-Williams integer N of 'key_length' bits with factorization p,q
        (p, q) = self.BWInt.generatePrimes(int(keyLength/2))
        # Generate random u,h \in QR_N and a random c \in {0,1}^|N|
        N = p * q
        u = randomQR(N)
        h = randomQR(N)
        c = randomBits(keyLength)#PRNG_generate_bits(key_length)

        K = self.Prf.keygen(keyLength)
        self.state = 0
    
        # Generate the Chameleon hash parameters.  We do not need the secret params.
        (L, secret) = self.ChameleonHash.paramgen(keyLength, p, q);
    
        # Assemble the public and secret keys
        pk = { 'length': keyLength, 'N': N, 'u': u, 'h': h, 'c': c, 'K': K, 'L': L }
        sk = { 'p': p, 'q': q }
        return (pk, sk);
    
    def sign(self, pk, sk, message, s=0):
        if debug: print("Sign...")
        L, K, c, keyLength, u, h, N = pk['L'], pk['K'], pk['c'], pk['length'], pk['u'], pk['h'], pk['N']
        p, q = sk['p'], sk['q']
        # Use internal state counter if none was provided
        if (s == 0):
          s = self.state
          self.state += 1
          s += 1

        # Hash the message using the chameleon hash under params L to obtain (x, r)
        (x, r) = self.ChameleonHash.hash(L, message);
        # Compute e = H_k(s) and check whether it's prime. If not, increment s and repeat.
        phi_N = (p-1)*(q-1)
        e = self.HW_hash(K, c, s, keyLength)
        e1 = e % phi_N
        e2 = e % N
        
        while (not (isPrime(e2))) or (not gcd(e1, phi_N) == 1):
            s += 1
            e = self.HW_hash(K, c, s, keyLength)
            e1 = e % phi_N
            e2 = e % N
        e = e1

        # Compute B = SQRT(u^x * h)^ceil(log_2(s)) mod N
        # Note that SQRT requires the factorization p, q
        temp = ((u ** x) * h) % N
        power = ((((p-1)*(q-1))+4)/8) ** (math.ceil(log[2](s)))
        B = temp ** power
        sigma1 = (B ** (e ** -1)) % N

        # Update internal state counter and return sig = (sigma1, r, s)
        self.state = s
        return { 'sigma1':sigma1, 'r': r, 's': s, 'e':e }


    def verify(self, pk, message, sig):
        if debug: print("\nVERIFY\n\n")
        sigma1, r, s, e = sig['sigma1'], sig['r'], sig['s'], sig['e']
        K, L, c, keyLength, u, h, N = pk['K'], pk['L'], pk['c'], pk['length'], pk['u'], pk['h'], pk['N']
    
        # Make sure that 0 < s < 2^{keylength/2}, else reject the signature
        if not (0 < s and s < (2 ** (keyLength/2))):
            return False

        # Compute e = H_k(s) and reject the signature if it's not prime
        ei = self.HW_hash(K, c, s, keyLength) % N
        if not isPrime(ei):
            if debug: print("ei not prime")
            return False
        
        # Compute Y = sigma1^{2*ceil(log2(s))}
        s1 = integer(2 ** (math.ceil(log[2](s))))
        Y = (sigma1 ** s1) % N
        
        # Hash the mesage using the chameleon hash with fixed randomness r
        (x, r2) = self.ChameleonHash.hash(L, message, r)

        lhs = (Y ** ei) % N
        rhs = ((u ** x) * h) % N
        if debug:
            print("lhs =>", lhs)
            print("rhs =>", rhs)
        # Verify that Y^e = (u^x h) mod N.  If so, accept the signature
        if lhs == rhs:
            return True
        # Default: reject the signature
        return False
    
    def HW_hash(self, key, c, input, keyLen):
        C = integer(c)
        input_size = bitsize(c)
        input_b = Conversion.IP2OS(input, input_size)
        # Return c XOR PRF(k, input), where the output of PRF is keyLength bits
        result = C ^ self.Prf.eval(key, input_b)
        return result
        
def main():
    pksig = Sig_RSA_Stateless_HW09() 

    (pk, sk) = pksig.keygen(1024)
    if debug:
        print("Public parameters...")
        print("pk =>", pk)
        print("sk =>", sk)
    
    m = SHA1(b'this is the message I want to hash.')
    m2 = SHA1(b'please sign this message too!')
    #m = b'This is a message to hash'
    sig = pksig.sign(pk, sk, m)
    if debug:
        print("Signature...")
        print("sig =>", sig)
    sig2 = pksig.sign(pk, sk, m2)
    if debug:
        print("Signature 2...")
        print("sig2 =>", sig2)
    
    assert pksig.verify(pk, m, sig), "FAILED VERIFICATION!!!"
    assert pksig.verify(pk, m2, sig2), "FAILED VERIFICATION!!!"
    if debug: print("Successful Verification!!!")

if __name__ == "__main__":
    debug = True
    main()   
