from setuptools import setup
pkg = "persistentmemo"
ver = "1.0.0"
setup(name         = pkg,
      version      = ver,
      description  = "Persistent memoization library",
      author       = "Eduard Christian Dumitrescu",
      license      = "MIT",
      url          = "https://github.com/e-c-d/persistentmemo",
      packages     = [pkg],
      classifiers  = ["Programming Language :: Python :: 3 :: Only",
                      "Topic :: Software Development :: Libraries :: Python Modules",
                      "Topic :: Software Development :: Build Tools"])
