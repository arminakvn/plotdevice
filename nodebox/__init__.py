__version__='1.9.8'

def get_version():
    return __version__

def bundle_path(subpath=None):
    """Find the path to the main NSBundle (or an optional subpath within it)"""
    from os.path import join
    from Foundation import NSBundle
    bundle = NSBundle.mainBundle().bundlePath()
    if subpath:
        return join(bundle, subpath)
    return bundle

def resource_path(resource=None):
    """Return absolute path of the rsrc directory (used by task.py)"""
    from os.path import abspath, dirname, exists, join
    module_root = abspath(dirname(__file__))
    rsrc_root = join(module_root, 'rsrc')

    if not exists(rsrc_root):
        # hack to run in-place in sdist
        from glob import glob
        for pth in glob(join(module_root, '../build/lib.*-2.7/nodebox/rsrc')):
            rsrc_root = abspath(pth)
            break
        else:
            notfound = "Couldn't locate resources directory (try running `python setup.py build` before running from the source dist)."
            raise RuntimeError(notfound)
    if resource:
        return join(rsrc_root, resource)
    return rsrc_root

def _startup():
    """Add the Extras directory to sys.path since every module depends on PyObjC and friends"""
    import sys
    try:
        import objc
    except ImportError:
        extras = '/System/Library/Frameworks/Python.framework/Versions/2.7/Extras/lib/python'
        sys.path.extend([extras, '%s/PyObjC'%extras])
        import objc

    # make sure we can find the c-extensions when run from the sdist
    try:
        import cGeo
    except ImportError:
        from os.path import abspath, dirname, join
        from glob import glob
        for pth in glob(join(abspath(dirname(__file__)), '../build/lib.*-2.7')):
            sys.path.append(abspath(pth))
            break
        else:
            notfound = "Couldn't locate C extension (try running `python setup.py build` before running from the source dist)."
            raise RuntimeError(notfound)

    # print python exceptions to the console rather than silently failing
    import objc
    objc.setVerbose(True) 

    # cleanup namespace
    global _startup
    del _startup


# flag will be set to true if we're running inside an NSApplication
app = False

# set up sys.path and enable error logging
_startup()
