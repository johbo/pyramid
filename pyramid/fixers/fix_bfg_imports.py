import os
import re
import sys

from lib2to3.refactor import get_fixers_from_package
from lib2to3.refactor import RefactoringTool
from lib2to3.fixer_util import Name
from lib2to3.fixer_util import attr_chain
from lib2to3 import fixer_base

MAPPING = {'repoze.bfg':'pyramid'}

for name in (
    'compat',
    'configuration',
    'authentication',
    'authorization',
    'chameleon_text',
    'chameleon_zpt',
    'decorator',
    'encode',
    'events',
    'exceptions',
    'i18n',
    'includes',
    'interfaces',
    'location',
    'log',
    'paster',
    'path',
    'registry',
    'renderers',
    'request',
    'resource',
    'router',
    'scripting',
    'security',
    'settings',
    'static',
    'testing',
    'tests',
    'tests.test_configuration',
    'tests.ccbugapp',
    'tests.exceptionviewapp',
    'repoze.bfg.tests.exceptionviewapp.models',
    'tests.fixtureapp',
    'tests.fixtureapp.models',
    'tests.grokkedapp',
    'tests.hybridapp',
    'tests.localeapp',
    'tests.restbugapp',
    'tests.routesapp',
    'threadlocal',
    'traversal',
    'urldispatch',
    'url',
    'view',
    'wsgi',
    'zcml',
    ):
    frm = 'repoze.bfg.' + name
    to =  'pyramid.' + name
    MAPPING[frm] = to

def alternates(members):
    return "(" + "|".join(map(str, members)) + ")"

def build_pattern(mapping=MAPPING):
    mod_list = []

    for key in mapping:
        splitted = key.split('.')
        joined = " '.' ".join(["'%s'" %s for s in splitted])
        mod_list.append(joined)

    mod_list = ' | '.join(
        ['module_name=dotted_name< %s >' %s for s in mod_list])

    yield """name_import=import_name< 'import' ((%s) |
               multiple_imports=dotted_as_names< any* (%s) any* >) >
          """ % (mod_list, mod_list)
    yield """import_from< 'from' (%s) 'import' ['(']
              ( any | import_as_name< any 'as' any > |
                import_as_names< any* >)  [')'] >
          """ % mod_list
    yield """import_name< 'import' (dotted_as_name< (%s) 'as' any > |
               multiple_imports=dotted_as_names<
                 any* dotted_as_name< (%s) 'as' any > any* >) >
          """ % (mod_list, mod_list)

    # Find usages of module members in code e.g. ``repoze.bfg`` or
    # ``repoze.bfg.configuration``
    # 'repoze' trailer< '.' 'bfg' > trailer< '.' 'configuration' >
    bare_names = []
    for key in mapping:
        splitted = key.split('.')
        tmp = ["'%s'" % splitted[0]]
        for thing in splitted[1:]:
            tmp.append(" trailer< '.' '%s' > " % thing)
        bare_name = ''.join(tmp)
        bare_names.append(bare_name)

    names = alternates(bare_names)
    yield "power< bare_with_attr=%s >" % names

class FixBfgImports(fixer_base.BaseFix):

    mapping = MAPPING
    run_order = 8

    def build_pattern(self):
        pattern = "|".join(build_pattern(self.mapping))
        return pattern

    def compile_pattern(self):
        # We override this, so MAPPING can be pragmatically altered and the
        # changes will be reflected in PATTERN.
        self.PATTERN = self.build_pattern()
        super(FixBfgImports, self).compile_pattern()

    # Don't match the node if it's within another match.
    def match(self, node):
        match = super(FixBfgImports, self).match
        results = match(node)
        if results:
            # Module usage could be in the trailer of an attribute lookup, so we
            # might have nested matches when "bare_with_attr" is present.
            if "bare_with_attr" not in results and \
                    any(match(obj) for obj in attr_chain(node, "parent")):
                return False
            return results
        return False

    def start_tree(self, tree, filename):
        super(FixBfgImports, self).start_tree(tree, filename)
        self.replace = {}

    def transform(self, node, results):
        # Mostly copied from fix_imports.py
        import_mod = results.get("module_name")
        if import_mod:
            try:
                mod_name = import_mod.value
            except AttributeError:
                # XXX: A hack to remove whitespace prefixes and suffixes
                mod_name = str(import_mod).strip()
            new_name = self.mapping[mod_name]
            import_mod.replace(Name(new_name, prefix=import_mod.prefix))
            if "name_import" in results:
                # If it's not a "from x import x, y" or "import x as y" import,
                # marked its usage to be replaced.
                self.replace[mod_name] = new_name
            if "multiple_imports" in results:
                # This is a nasty hack to fix multiple imports on a line (e.g.,
                # "import StringIO, urlparse"). The problem is that I can't
                # figure out an easy way to make a pattern recognize the keys of
                # MAPPING randomly sprinkled in an import statement.
                results = self.match(node)
                if results:
                    self.transform(node, results)
        else:
            # Replace usage of the module.
            bare_name_text = ''.join(map(str,results['bare_with_attr'])).strip()
            new_name = self.replace.get(bare_name_text)
            bare_name = results["bare_with_attr"][0]

            if new_name:
                node.replace(Name(new_name, prefix=bare_name.prefix))

BFG_INCLUDES_RE = (
    r'include\s+?package\s*?=\s*?[\'\"]repoze\.bfg\.includes[\'\"]')
BFG_NS_RE = (
    r'xmlns\s*?=\s*?[\'\"]http://namespaces\.repoze\.org/bfg[\'\"]')

INCLUDES = re.compile(BFG_INCLUDES_RE, re.MULTILINE)
NS = re.compile(BFG_NS_RE, re.MULTILINE)

def fix_zcml(path):
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.endswith('.zcml'):
                absfile = os.path.join(root, file)
                text = open(absfile, 'rb').read()
                newt =INCLUDES.sub('include package="pyramid.includes"', text)
                newt = NS.sub('xmlns="http://pylonshq.com/pyramid"', newt)
                if text != newt:
                    newf = open(absfile, 'wb')
                    newf.write(newt)
                    newf.flush()
                    newf.close()
                
        for dir in dirs:
            if dir.startswith('.'):
                dirs.remove(dir)

def main(argv=None):
    if argv is None:
        argv = sys.argv
    path = argv[1]
    fixer_names = get_fixers_from_package('pyramid.fixers')
    tool = RefactoringTool(fixer_names)
    tool.refactor([path], write=True)
    fix_zcml(path)

if __name__ == '__main__':
    main()
    
