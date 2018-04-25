# -*- coding: utf-8 -*-
# Author: Óscar Nájera
# License: 3-clause BSD
"""
Link resolver objects
=====================
"""
from __future__ import print_function
import codecs
import gzip
import os
import posixpath
import re
import shelve
import sys

# Try Python 2 first, otherwise load from Python 3
try:
    import cPickle as pickle
except ImportError:
    import pickle
try:
    import urllib2 as urllib_request
    from urllib2 import HTTPError, URLError
    import urlparse as urllib_parse
except ImportError:
    import urllib.request as urllib_request
    import urllib.parse as urllib_parse
    from urllib.error import HTTPError, URLError

from io import BytesIO

from sphinx.search import js_index

from . import sphinx_compatibility


logger = sphinx_compatibility.getLogger('sphinx-gallery')


def _get_data(url):
    """Helper function to get data over http(s) or from a local file"""
    if urllib_parse.urlparse(url).scheme in ('http', 'https'):
        resp = urllib_request.urlopen(url)
        encoding = resp.headers.get('content-encoding', 'plain')
        data = resp.read()
        if encoding == 'plain':
            data = data.decode('utf-8')
        elif encoding == 'gzip':
            data = BytesIO(data)
            data = gzip.GzipFile(fileobj=data).read().decode('utf-8')
        else:
            raise RuntimeError('unknown encoding')
    else:
        with codecs.open(url, mode='r', encoding='utf-8') as fid:
            data = fid.read()

    return data


def get_data(url, gallery_dir):
    """Persistent dictionary usage to retrieve the search indexes"""

    # shelve keys need to be str in python 2
    if sys.version_info[0] == 2 and isinstance(url, unicode):
        url = url.encode('utf-8')

    cached_file = os.path.join(gallery_dir, 'searchindex')
    search_index = shelve.open(cached_file)
    if url in search_index:
        data = search_index[url]
    else:
        data = _get_data(url)
        search_index[url] = data
    search_index.close()

    return data


def parse_sphinx_docopts(index):
    """
    Parse the Sphinx index for documentation options.

    Parameters
    ----------
    index : str
        The Sphinx index page

    Returns
    -------
    docopts : dict
        The documentation options from the page.
    """

    pos = index.find('DOCUMENTATION_OPTIONS')
    if pos < 0:
        raise ValueError('Documentation options could not be found in index.')
    pos = index.find('{', pos)
    if pos < 0:
        raise ValueError('Documentation options could not be found in index.')
    endpos = index.find('};', pos)
    if endpos < 0:
        raise ValueError('Documentation options could not be found in index.')
    block = index[pos + 1:endpos].strip()
    docopts = {}
    for line in block.splitlines():
        key, value = line.split(':', 1)
        key = key.strip().strip('"')

        value = value.strip()
        if value[-1] == ',':
            value = value[:-1].rstrip()
        if value[0] in '"\'':
            value = value[1:-1]
        elif value == 'false':
            value = False
        elif value == 'true':
            value = True
        else:
            value = int(value)

        docopts[key] = value

    return docopts


class SphinxDocLinkResolver(object):
    """ Resolve documentation links using searchindex.js generated by Sphinx

    Parameters
    ----------
    doc_url : str
        The base URL of the project website.
    relative : bool
        Return relative links (only useful for links to documentation of this
        package).
    """

    def __init__(self, doc_url, gallery_dir, relative=False):
        self.doc_url = doc_url
        self.gallery_dir = gallery_dir
        self.relative = relative
        self._link_cache = {}

        if doc_url.startswith(('http://', 'https://')):
            if relative:
                raise ValueError('Relative links are only supported for local '
                                 'URLs (doc_url cannot be absolute)')
            index_url = doc_url + '/'
            searchindex_url = doc_url + '/searchindex.js'
            docopts_url = doc_url + '_static/documentation_options.js'
        else:
            index_url = os.path.join(doc_url, 'index.html')
            searchindex_url = os.path.join(doc_url, 'searchindex.js')
            docopts_url = os.path.join(doc_url, '_static', 'documentation_options.js')

        # detect if we are using relative links on a Windows system
        if (os.name.lower() == 'nt' and
                not doc_url.startswith(('http://', 'https://'))):
            if not relative:
                raise ValueError('You have to use relative=True for the local'
                                 ' package on a Windows system.')
            self._is_windows = True
        else:
            self._is_windows = False

        # Download and find documentation options. As of Sphinx 1.7, these
        # options are now kept in a standalone file called
        # 'documentation_options.js'. Since SphinxDocLinkResolver can be called
        # not only for the documentation which is being built but also ones that
        # are being referenced, we need to try and get the index page first and
        # if that doesn't work, check for the documentation_options.js file.
        index = get_data(index_url, gallery_dir)
        if 'DOCUMENTATION_OPTIONS' in index:
            self._docopts = parse_sphinx_docopts(index)
        else:
            docopts = get_data(docopts_url, gallery_dir)
            self._docopts = parse_sphinx_docopts(docopts)

        # download and initialize the search index
        sindex = get_data(searchindex_url, gallery_dir)
        self._searchindex = js_index.loads(sindex)

    def _get_link(self, cobj):
        """Get a valid link, False if not found"""

        fullname = cobj['module_short'] + '.' + cobj['name']
        try:
            value = self._searchindex['objects'][cobj['module_short']]
            match = value[cobj['name']]
        except KeyError:
            link = False
        else:
            fname_idx = match[0]
            objname_idx = str(match[1])
            anchor = match[3]

            fname = self._searchindex['filenames'][fname_idx]
            # In 1.5+ Sphinx seems to have changed from .rst.html to only
            # .html extension in converted files. Find this from the options.
            ext = self._docopts.get('FILE_SUFFIX', '.rst.html')
            fname = os.path.splitext(fname)[0] + ext
            if self._is_windows:
                fname = fname.replace('/', '\\')
                link = os.path.join(self.doc_url, fname)
            else:
                link = posixpath.join(self.doc_url, fname)

            if anchor == '':
                anchor = fullname
            elif anchor == '-':
                anchor = (self._searchindex['objnames'][objname_idx][1] + '-' +
                          fullname)

            link = link + '#' + anchor

        return link

    def resolve(self, cobj, this_url):
        """Resolve the link to the documentation, returns None if not found

        Parameters
        ----------
        cobj : dict
            Dict with information about the "code object" for which we are
            resolving a link.
            cobj['name'] : function or class name (str)
            cobj['module_short'] : shortened module name (str)
            cobj['module'] : module name (str)
        this_url: str
            URL of the current page. Needed to construct relative URLs
            (only used if relative=True in constructor).

        Returns
        -------
        link : str | None
            The link (URL) to the documentation.
        """
        full_name = cobj['module_short'] + '.' + cobj['name']
        link = self._link_cache.get(full_name, None)
        if link is None:
            # we don't have it cached
            link = self._get_link(cobj)
            # cache it for the future
            self._link_cache[full_name] = link

        if link is False or link is None:
            # failed to resolve
            return None

        if self.relative:
            link = os.path.relpath(link, start=this_url)
            if self._is_windows:
                # replace '\' with '/' so it on the web
                link = link.replace('\\', '/')

            # for some reason, the relative link goes one directory too high up
            link = link[3:]

        return link


def _embed_code_links(app, gallery_conf, gallery_dir):
    # Add resolvers for the packages for which we want to show links
    doc_resolvers = {}

    src_gallery_dir = os.path.join(app.builder.srcdir, gallery_dir)
    for this_module, url in gallery_conf['reference_url'].items():
        try:
            if url is None:
                doc_resolvers[this_module] = SphinxDocLinkResolver(
                    app.builder.outdir, src_gallery_dir, relative=True)
            else:
                doc_resolvers[this_module] = SphinxDocLinkResolver(
                    url, src_gallery_dir)

        except HTTPError as e:
            logger.warning(
                'The following HTTP Error has occurred fetching %s: %d %s',
                e.url, e.code, e.msg)
        except URLError as e:
            logger.warning(
                "Embedding the documentation hyperlinks requires Internet "
                "access.\nPlease check your network connection.\nUnable to "
                "continue embedding `%s` links due to a URL Error:\n%s",
                this_module,
                str(e.args))

    html_gallery_dir = os.path.abspath(os.path.join(app.builder.outdir,
                                                    gallery_dir))

    # patterns for replacement
    link_pattern = ('<a href="%s" title="View documentation for %s">%s</a>')
    orig_pattern = '<span class="n">%s</span>'
    period = '<span class="o">.</span>'

    # This could be turned into a generator if necessary, but should be okay
    flat = [[dirpath, filename]
            for dirpath, _, filenames in os.walk(html_gallery_dir)
            for filename in filenames]
    iterator = sphinx_compatibility.status_iterator(
        flat, 'embedding documentation hyperlinks for %s... ' % gallery_dir,
        color='fuchsia', length=len(flat),
        stringify_func=lambda x: os.path.basename(x[1]))
    intersphinx_inv = getattr(app.env, 'intersphinx_named_inventory', dict())
    for dirpath, fname in iterator:
        full_fname = os.path.join(html_gallery_dir, dirpath, fname)
        subpath = dirpath[len(html_gallery_dir) + 1:]
        pickle_fname = os.path.join(src_gallery_dir, subpath,
                                    fname[:-5] + '_codeobj.pickle')

        if os.path.exists(pickle_fname):
            # we have a pickle file with the objects to embed links for
            with open(pickle_fname, 'rb') as fid:
                example_code_obj = pickle.load(fid)
            fid.close()
            str_repl = {}
            # generate replacement strings with the links
            for name, cobj in example_code_obj.items():
                this_module = cobj['module'].split('.')[0]

                # Try doc resolvers first
                link = None
                if this_module in doc_resolvers:
                    try:
                        link = doc_resolvers[this_module].resolve(cobj,
                                                                  full_fname)
                    except (HTTPError, URLError) as e:
                        if isinstance(e, HTTPError):
                            extra = e.code
                        else:
                            extra = e.reason
                        logger.warning("Error resolving %s.%s: %r (%s)",
                                       cobj['module'], cobj['name'], e, extra)
                        link = None

                # next try intersphinx
                if link is None and this_module in intersphinx_inv:
                    inv = app.env.intersphinx_named_inventory[this_module]
                    want = '%s.%s' % (cobj['module'], cobj['name'])
                    for value in inv.values():
                        if want in value:
                            link = value[want][2]
                            break

                if link is not None:
                    parts = name.split('.')
                    name_html = period.join(orig_pattern % part
                                            for part in parts)
                    full_function_name = '%s.%s' % (
                        cobj['module'], cobj['name'])
                    str_repl[name_html] = link_pattern % (
                        link, full_function_name, name_html)

            # do the replacement in the html file

            # ensure greediness
            names = sorted(str_repl, key=len, reverse=True)
            regex_str = '|'.join(re.escape(name) for name in names)
            regex = re.compile(regex_str)

            def substitute_link(match):
                return str_repl[match.group()]

            if len(str_repl) > 0:
                with open(full_fname, 'rb') as fid:
                    lines_in = fid.readlines()
                with open(full_fname, 'wb') as fid:
                    for line in lines_in:
                        line = line.decode('utf-8')
                        line = regex.sub(substitute_link, line)
                        fid.write(line.encode('utf-8'))


def embed_code_links(app, exception):
    """Embed hyperlinks to documentation into example code"""
    if exception is not None:
        return

    # No need to waste time embedding hyperlinks when not running the examples
    # XXX: also at the time of writing this fixes make html-noplot
    # for some reason I don't fully understand
    if not app.builder.config.plot_gallery:
        return

    # XXX: Whitelist of builders for which it makes sense to embed
    # hyperlinks inside the example html. Note that the link embedding
    # require searchindex.js to exist for the links to the local doc
    # and there does not seem to be a good way of knowing which
    # builders creates a searchindex.js.
    if app.builder.name not in ['html', 'readthedocs']:
        return

    logger.info('embedding documentation hyperlinks...', color='white')

    gallery_conf = app.config.sphinx_gallery_conf

    gallery_dirs = gallery_conf['gallery_dirs']
    if not isinstance(gallery_dirs, list):
        gallery_dirs = [gallery_dirs]

    for gallery_dir in gallery_dirs:
        _embed_code_links(app, gallery_conf, gallery_dir)
