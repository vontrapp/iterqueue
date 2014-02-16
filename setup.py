#!/usr/bin/env python

from distutils.core import setup

setup(name="python-iterqueue",
      version="0.2",
      author="Von Fugal",
      author_email="von@fugal.net",
      py_modules=["IterQueue"],
      license="Open Source",
      url="http://github.com/vontrapp/iterqueue",
      description="A synchronization queue that can be used as an iterable",
      long_description="""A drop in replacement for the python Queue that can be used as an iterable.
e.g.
  q = IterQueue.Queue()
  for i in range(4):
    t = Thread(target=lambda: for item in q: process(item))
    t.start()
  map(q.put, items)
  q.close()

Closing the q causes the iterations to stop once the q is empty"""
     )
