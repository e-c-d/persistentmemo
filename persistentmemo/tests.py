import unittest
from . import *

class PersistentMemoTest(unittest.TestCase):
    def test_all(self):
        m = PersistentMemo()
        m.store = {}
        called = 0
        x = []
        @fdeps(x, set_readonly=False)
        def f(x,y,**kw):
            nonlocal called
            called += 1
            return (x+y,list(kw))
        mf = m.memoize()(f)
        mf(3,5)
        mf(3,5)
        self.assertEqual(called, 1)
        mf(3,4)
        self.assertEqual(called, 2)
        mf([4],['x',4.4])
        mf([4],['x',4.4])
        mf([4],['x',4.40001])
        self.assertEqual(called, 4)
        self.assertEqual(mf(3,4,w=[7]), mf(3,4,w=[7]))
        self.assertEqual(called, 5)
        called = 0
        x.append(0)
        mf(3,5)
        self.assertEqual(called, 1)
        m.set_readonly(f)
        mf(3,5)
        called = 0
        mf(3,5)
        self.assertEqual(called, 0)
        x.append(0)
        self.assertEqual(called, 0)
