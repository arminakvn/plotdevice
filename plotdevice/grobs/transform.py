# encoding: utf-8
import os
import re
import json
import warnings
import math
from AppKit import *
from Foundation import *
from Quartz import *

from plotdevice import DeviceError
from ..util import trim_zeroes
from ..lib import geometry

_ctx = None
__all__ = [
        "DEGREES", "RADIANS", "PERCENT",
        "inch", "cm", "mm", "pi", "tau",
        "Point", "Size", "Region",
        "Transform", "CENTER", "CORNER",
        ]

# scale factors
inch = 72
cm = 28.3465
mm = 2.8346
pi = math.pi
tau = 2*pi

# transform modes
CENTER = "center"
CORNER = "corner"

# rotation modes
DEGREES = "degrees"
RADIANS = "radians"
PERCENT = "percent"

### tuple-like objects for grid dimensions ###

class Point(object):
    def __init__(self, *args):
        if len(args) == 2:
            self.x, self.y = args
        elif len(args) == 1:
            self.x, self.y = args[0]
        elif len(args) == 0:
            self.x = self.y = 0.0
        else:
            badcoords = "Bad initial coordinates for Point object"
            raise DeviceError(badcoords)

    @trim_zeroes
    def __repr__(self):
        return "Point(x=%.3f, y=%.3f)" % (self.x, self.y)

    def __eq__(self, other):
        if other is None: return False
        return self.x == other.x and self.y == other.y

    def __ne__(self, other):
        return not self.__eq__(other)

    def __iter__(self):
        # allow for assignments like: x,y = Point()
        return iter([self.x, self.y])

    # lib.geometry methods (accept either x,y pairs or Point args)

    def angle(self, x=0, y=0):
        if isinstance(x, Point):
            x, y = x.__iter__()
        return geometry.angle(self.x, self.y, x, y)

    def distance(self, x=0, y=0):
        if isinstance(x, Point):
            x, y = x.__iter__()
        return geometry.distance(self.x, self.y, x, y)

    def reflect(self, x=0, y=0, d=1.0, a=180):
        if isinstance(x, Point):
            d, a = y, d
            x, y = x.__iter__()
        return geometry.reflect(self.x, self.y, x, y, d, a)

    def coordinates(self, distance, angle):
        return geometry.coordinates(self.x, self.y, distance, angle)

class Size(tuple):
    def __new__(cls, width, height):
        this = tuple.__new__(cls, (width, height))
        for attr in ('w','width'): setattr(this, attr, width)
        for attr in ('h','height'): setattr(this, attr, height)
        return this

    @trim_zeroes
    def __repr__(self):
        return 'Size(width=%.3f, height=%.3f)'%self

class Region(tuple):
    # Bug?: maybe this actually needs to be mutable...
    def __new__(cls, x=0, y=0, w=0, h=0, **kwargs):
        if isinstance(x, NSRect):
            return Region(*x)

        try: # accept a pair of 2-tuples as origin/size
            (x,y), (width,height) = x,y
        except TypeError:
            # accept both w/h and width/height spellings
            width = kwargs.get('width', w)
            height = kwargs.get('height', h)
        this = tuple.__new__(cls, [(x,y), (width, height)])
        for nm in ('x','y','width','height'):
            if nm[1:]: setattr(this, nm[0], locals()[nm])
            setattr(this, nm, locals()[nm])
        this.origin = Point(x,y)
        this.size = Size(width, height)
        return this

    @trim_zeroes
    def __repr__(self):
        return 'Region(x=%.3f, y=%.3f, w=%.3f, h=%.3f)'%(self[0]+self[1])


### NSAffineTransform wrapper used for positioning Grobs in a Context ###

class Transform(object):

    def __init__(self, transform=None):
        if transform is None:
            transform = NSAffineTransform.transform()
        elif isinstance(transform, Transform):
            transform = transform._nsAffineTransform.copy()
        elif isinstance(transform, NSAffineTransform):
            transform = transform.copy()
        elif isinstance(transform, (list, tuple, NSAffineTransformStruct)):
            struct = tuple(transform)
            transform = NSAffineTransform.transform()
            transform.setTransformStruct_(struct)
        else:
            wrongtype = "Don't know how to handle transform %s." % transform
            raise DeviceError(wrongtype)
        self._nsAffineTransform = transform

    def __enter__(self):
        # Transform objects get _rollback attrs when they're derived from the graphics
        # context's current transform via a state-mutation command. In these cases
        # the global state has already been changed before the context manager was
        # invoked, so don't re-apply it again here.
        if not hasattr(self, '_rollback'):
            _ctx._transform.prepend(self)

    def __exit__(self, type, value, tb):
        # once we've been through a block the _rollback (if any) can be discarded
        if hasattr(self, '_rollback'):
            # _rollback is a dict containing any of _transform, _transformmode,
            # and _rotationmode. in these cases do a direct overwrite then bail
            # out rather than applying the inverse transform
            for attr, priorval in self._rollback.items():
                setattr(_ctx, attr, priorval)
            del self._rollback
            return
        else:
            # restore the context's transform
            _ctx._transform.prepend(self.inverse)

    @trim_zeroes
    def __repr__(self):
        return "%s([%.3f, %.3f, %.3f, %.3f, %.3f, %.3f])" % ((self.__class__.__name__,)
                 + tuple(self))

    def __iter__(self):
        for value in self._nsAffineTransform.transformStruct():
            yield value

    def copy(self):
        return self.__class__(self)

    def _get_matrix(self):
        return self._nsAffineTransform.transformStruct()
    def _set_matrix(self, value):
        self._nsAffineTransform.setTransformStruct_(value)
    matrix = property(_get_matrix, _set_matrix)

    @property
    def inverse(self):
        inv = self.copy()
        inv._nsAffineTransform.invert()
        return inv

    def rotate(self, degrees=0, radians=0, **opt):
        xf = Transform()
        if degrees:
            xf._nsAffineTransform.rotateByDegrees_(degrees)
        else:
            xf._nsAffineTransform.rotateByRadians_(radians)
        if opt.get('rollback'):
            xf._rollback = {"_transform":self.copy()}
        self.prepend(xf)
        return xf

    def translate(self, x=0, y=0, **opt):
        xf = Transform()
        xf._nsAffineTransform.translateXBy_yBy_(x, y)
        if opt.get('rollback'):
            xf._rollback = {"_transform":self.copy()}
        self.prepend(xf)
        return xf

    def scale(self, x=1, y=None, **opt):
        if y is None:
            y = x
        xf = Transform()
        xf._nsAffineTransform.scaleXBy_yBy_(x, y)
        if opt.get('rollback'):
            xf._rollback = {"_transform":self.copy()}
        self.prepend(xf)
        return xf

    def skew(self, x=0, y=0, **opt):
        x,y = map(lambda n: n*pi/180, [x,y])
        xf = Transform()
        xf.matrix = (1, math.tan(y), -math.tan(x), 1, 0, 0)
        if opt.get('rollback'):
            xf._rollback = {"_transform":self.copy()}
        self.prepend(xf)
        return xf

    def set(self):
        self._nsAffineTransform.set()

    def concat(self):
        self._nsAffineTransform.concat()

    def append(self, other):
        if isinstance(other, Transform):
            other = other._nsAffineTransform
        self._nsAffineTransform.appendTransform_(other)

    def prepend(self, other):
        if isinstance(other, Transform):
            other = other._nsAffineTransform
        self._nsAffineTransform.prependTransform_(other)

    def apply(self, point_or_path):
        from .bezier import Bezier
        if isinstance(point_or_path, Bezier):
            return self.transformBezier(point_or_path)
        elif isinstance(point_or_path, Point):
            return self.transformPoint(point_or_path)
        else:
            wrongtype = "Can only transform Beziers or Points"
            raise DeviceError(wrongtype)

    def transformPoint(self, point):
        return Point(self._nsAffineTransform.transformPoint_((point.x,point.y)))

    def transformBezier(self, path):
        from .bezier import Bezier
        if isinstance(path, Bezier):
            path = Bezier(path)
        else:
            wrongtype = "Can only transform Beziers"
            raise DeviceError(wrongtype)
        path._nsBezierPath = self._nsAffineTransform.transformBezierPath_(path._nsBezierPath)
        return path

    def transformBezierPath(self, path):
        return self.transformBezier(path)

    @property
    def transform(self):
        warnings.warn("The 'transform' attribute is deprecated. Please use _nsAffineTransform instead.", DeprecationWarning, stacklevel=2)
        return self._nsAffineTransform
