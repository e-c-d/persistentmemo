import functools, weakref, io, pickle, hashlib, copyreg, inspect
import warnings
from types import FunctionType, CodeType

__doc__ = """Persistent memoization

Example usage:

from persistentmemo import PersistentMemo, PersistentMemoStoreRedis, fdeps

memo = PersistentMemo()
memoize = memo.memoize

PI = 3.14

@fdeps(PI)
def foo(x, y):
    return x * (y - PI)

@memoize()
@fdeps(foo)
def bar(z):
    return foo(z, z+1) + 2

# mandatory fibonacci example
@memoize()
def fibs(n):
    if n==0 or n==1: return n
    return fibs(n-1) + fibs(n-2)

def init_persistentmemo():
    import redis
    redis_pool = redis.ConnectionPool(host='127.0.0.1',port=6379)
    redis_obj = redis.StrictRedis(connection_pool=redis_pool)
    memo.store = PersistentMemoStoreRedis(redis_obj)

def main():
    init_persistentmemo()
    # or you could just do "memo.store = {}"
    print(bar(4), bar(4))
    print(fibs(300))
"""
__all__ = ['PersistentMemo', 'fdeps',
           'PersistentMemoStoreRedis']

class _RefBox(object):
    #__slots__ = ['value','__weakref__']
    __slots__ = ['value']
    def __init__(self, value):
        self.value = value
    def __hash__(self):
        return id(self.value)
    def __eq__(self, x):
        self_value_id = id(self.value)
        return ((type(x) == type(self) and self_value_id == id(x.value))
                or self_value_id == id(x))
    def __repr__(self):
        return repr(self.value)

class _Pickle_Hash(object):
    """This is only used to mark already-hashed objects in hash_serialize"""
class _Pickle_Function(object):
    """This is only used to mark functions in hash_serialize"""
class _Pickle_Code(object):
    """This is only used to mark code objects in hash_serialize"""
class _Pickle_FDeps(object):
    """This is only used to mark FDeps objects in hash_serialize"""

class _HashIO(object):
    def __init__(self, h):
        self.h = h
    def write(self, s):
        self.h.update(s)

def fdeps(*deps, use_eval=False, set_readonly=True):
    deps = tuple(deps)
    def wrapper(func):
        class FDeps(object):
            __call__ = staticmethod(func)
            __persistentmemo_readonly__ = set_readonly
            def __init__(self):
                self.deps = deps
                self.do_eval = use_eval
                functools.update_wrapper(self, self.__call__)
            @property
            def __memo_extra_dep__(self):
                if self.do_eval:
                    mod_dict = inspect.getmodule(self.__wrapped__).__dict__
                    self.deps = tuple(eval(x, mod_dict) if type(x) is str else x
                                      for x in self.deps)
                    self.do_eval = False
                return self.deps
            def __reduce__(self):
                return (_Pickle_FDeps,
                        (self.__call__, self.__memo_extra_dep__))
        return FDeps()
    return wrapper

class PersistentMemoStoreRedis(object):
    def __init__(self, redis, *,
                 prefix1=b"persistentmemo:md5:",
                 prefix2=b":"):
        self._prefix = prefix1 + prefix2
        self._redis = redis
    def __getitem__(self, key):
        v = self._redis.get(self._prefix+key)
        if v is None: raise KeyError
        return v
    def __setitem__(self, key, value):
        self._redis.set(self._prefix+key, value)

class PersistentMemo(object):
    """persistent memoization
self.store must implement __getitem__ and __setitem__"""
    _redis = None
    store = None
    def __init__(self):
        #self._cached_hash = weakref.WeakKeyDictionary()
        self._cached_hash = {}
    def hash_serialize(self, obj, file):
        class HashPickler(pickle._Pickler):
            pm = self
            def __init__(self, *args, **kwargs):
                self.dispatch = self.dispatch.copy()
                dispatch_table = copyreg.dispatch_table.copy()
                dispatch_table[dict] = self.reduce_dict
                dispatch_table[set] = self.reduce_set
                dispatch_table[frozenset] = self.reduce_set
                dispatch_table[CodeType] = self.reduce_code
                dispatch_table[FunctionType] = self.reduce_function
                for k in dispatch_table:
                    self.dispatch.pop(k, None)
                self.dispatch_table = dispatch_table
                super().__init__(*args, **kwargs)
            @staticmethod
            def reduce_dict(obj):
                return (type(obj), (), None, None,
                        sorted(obj.items()))
            @staticmethod
            def reduce_set(obj):
                return (type(obj), (), None,
                        sorted(obj))
            @staticmethod
            def reduce_function(obj):
                return (_Pickle_Function,
                        (obj.__code__,
                         getattr(obj,'__wrapped__', None)))
            @staticmethod
            def reduce_code(obj):
                return (_Pickle_Code,
                        ([getattr(obj,k) for k in
                         ('co_argcount','co_cellvars','co_code','co_consts',
                          'co_flags','co_freevars','co_kwonlyargcount',
                          'co_name','co_names','co_nlocals','co_stacksize',
                          'co_varnames')],))
            def persistent_id(self, obj):
                obj_refbox = _RefBox(obj)
                try:
                    cached_hash = self.pm._cached_hash[obj_refbox]
                except KeyError:
                    if getattr(obj, '__persistentmemo_readonly__', False):
                        self.pm.set_readonly(obj)
                        cached_hash = self.pm._cached_hash[obj_refbox]
                    else:
                        cached_hash = None
                if cached_hash is None:
                    return None
                else:
                    return (_Pickle_Hash, cached_hash)
        p = HashPickler(file=file)
        p.dump(obj)
    def hash(self, obj):
        try:
            return self._cached_hash[_RefBox(obj)]
        except KeyError:
            pass
        h = hashlib.md5()
        self.hash_serialize(obj, file=_HashIO(h))
        return h.digest()
    def serialize(self, obj):
        """this is used for function results; you may override this"""
        return pickle.dumps(obj, protocol=3)
    def deserialize(self, buf):
        """this is used for function results; you may override this"""
        return pickle.loads(buf)
    def set_readonly(self, obj, readonly=True):
        if readonly:
            self._cached_hash[_RefBox(obj)] = None
            self._cached_hash[_RefBox(obj)] = self.hash(obj)
        else:
            self._cached_hash.pop(_RefBox(obj), None)
        return obj
    def memoize(self):
        def wrapper(func):
            @functools.wraps(func)
            def wrapped(*args, **kwargs):
                S = self.store
                if S is None:
                    warnings.warn("you must set self.store to something that implements __getitem__ and __setitem__; without it there will be no caching")
                    return func(*args, **kwargs)
                call_data = [func, args, kwargs]
                key = self.hash(call_data)
                try:
                    value = S[key]
                except KeyError:
                    pass
                else:
                    return self.deserialize(value)
                result = func(*args, **kwargs)
                S[key] = self.serialize(result)
                return result
            return wrapped
        return wrapper
