#!/usr/bin/env python
#
# Copyright 2013 Mike Wakerly <opensource@hoho.com>
#
# This file is part of the Pykeg package of the Kegbot project.
# For more information on Pykeg or Kegbot, see http://kegbot.org/
#
# Pykeg is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License, or
# (at your option) any later version.
#
# Pykeg is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Pykeg.  If not, see <http://www.gnu.org/licenses/>.

"""Kegbot Server setup program."""

from __future__ import absolute_import

import os
import sys
import gflags
import getpass
import pprint
import subprocess

from kegbot.util import app

gflags.DEFINE_boolean('interactive', True,
    'Run in interactive mode.')

gflags.DEFINE_string('settings_file', '~/.kegbot/local_settings.py',
    'Settings file.')

gflags.DEFINE_string('data_root', '~/kegbot-data',
    'Data root for Kegbot.')

gflags.DEFINE_string('db_type', 'sqlite',
    'One of: mysql, sqlite.')

gflags.DEFINE_string('mysql_user', 'root',
    'MySQL username.  Ignored if using sqlite.')

gflags.DEFINE_string('mysql_password', '',
    'MySQL password.  Ignored if using sqlite.')

gflags.DEFINE_string('mysql_database', 'kegbot',
    'MySQL database name.  Ignored if using sqlite.')

gflags.DEFINE_string('sqlite_file', 'kegbot.sqlite',
    'File name for the Kegbot sqlite database within `data_root`.  Ignored if using MySQL.')

gflags.DEFINE_string('timezone', 'America/Los_Angeles',
    'Default time zone.')

FLAGS = gflags.FLAGS

SETTINGS_TEMPLATE = """# Kegbot local settings.
# Auto-generated, but safe to edit by hand.
# See http://kegbot.org/docs/server/ for more info.

# NEVER set DEBUG to `True` in production.
DEBUG = True
TEMPLATE_DEBUT = DEBUG

"""

class FatalError(Exception):
  """Cannot proceed."""

def trim(docstring):
  """Docstring trimming function, per PEP 257."""
  if not docstring:
    return ''
  # Convert tabs to spaces (following the normal Python rules)
  # and split into a list of lines:
  lines = docstring.expandtabs().splitlines()
  # Determine minimum indentation (first line doesn't count):
  indent = sys.maxint
  for line in lines[1:]:
    stripped = line.lstrip()
    if stripped:
      indent = min(indent, len(line) - len(stripped))
  # Remove indentation (first line is special):
  trimmed = [lines[0].strip()]
  if indent < sys.maxint:
    for line in lines[1:]:
      trimmed.append(line[indent:].rstrip())
  # Strip off trailing and leading blank lines:
  while trimmed and not trimmed[-1]:
    trimmed.pop()
  while trimmed and not trimmed[0]:
    trimmed.pop(0)
  # Return a single string:
  return '\n'.join(trimmed)

### Setup steps

# These define the actual prompts taken during setup.

class SetupStep(object):
  """A step in Kegbot server configuration.

  The base class has no user interface (flags or prompt); see
  ConfigurationSetupStep for that.
  """
  def get_docs(self):
    """Returns the prompt description text."""
    return trim(self.__doc__)

  def get(self, interactive, ctx):
    if interactive:
      docs = self.get_docs()
      print '-'*80
      print '\n'.join(docs.splitlines()[2:])
      print ''
      print ''

  def validate(self, ctx):
    """Validates user input.

    Args:
      ctx: context
    Raises:
      ValueError: on illegal value
    """
    ctx[self.__class__] = self.value

  def apply(self, ctx):
    pass

  def save(self, ctx):
    pass

  def add_to_settings(self, ctx, outfd):
    pass


class ConfigurationSetupStep(SetupStep):
  """A SetupStep that gets and/or applies some configuration value."""
  FLAG = None
  CHOICES = []

  def __init__(self):
    super(ConfigurationSetupStep, self).__init__()
    self.value = None

  def do_prompt(self, prompt, choices=[], default=None):
    """Prompts for and returns a value."""
    choices_text = ''
    if choices:
      choices_text = ' (%s)' % ', '.join(choices)

    default_text = ''
    if default is not None:
      default_text = ' [%s]' % default

    prompt_text = '%s%s%s: ' % (prompt, choices_text, default_text)

    value = raw_input(prompt_text)
    if value == '':
      return default
    return value

  def get_default(self, ctx):
    return self.get_from_flag(ctx)

  def get_from_prompt(self, ctx):
    docs = self.get_docs()
    return self.do_prompt(docs.splitlines()[0], self.CHOICES,
        self.get_default(ctx))

  def get_from_flag(self, ctx):
    if self.FLAG:
      return getattr(FLAGS, self.FLAG)
    return None

  def get(self, interactive, ctx):
    super(ConfigurationSetupStep, self).get(interactive, ctx)
    if interactive:
      ret = self.get_from_prompt(ctx)
    else:
      ret = self.get_from_flag(ctx)
    self.value = ret

  def validate(self, ctx):
    if self.CHOICES and self.value not in self.CHOICES:
      raise ValueError('Value must be one of: %s' % ', '.join(self.CHOICES))
    super(ConfigurationSetupStep, self).validate(ctx)

  def save(self, ctx):
    ctx[self.__class__] = self.value

  def apply(self, ctx):
    pass

### Main Steps

class RequiredLibraries(SetupStep):
  def validate(self, ctx):
    try:
        from PIL import Image, ImageColor, ImageChops, ImageEnhance, ImageFile, \
                ImageFilter, ImageDraw, ImageStat
    except ImportError:
        try:
            import Image
            import ImageColor
            import ImageChops
            import ImageEnhance
            import ImageFile
            import ImageFilter
            import ImageDraw
            import ImageStat
        except ImportError:
            raise FatalError('Could not locate Python Imaging Library, '
                'please install it ("pip install pillow" or "apt-get install python-imaging")')


class SettingsPath(ConfigurationSetupStep):
  """Select the settings file location.

  Kegbot's master settings file for this system (local_settings.py) should live
  in one of two places on the filesystem:

    ~/.kegbot/local_settings.py     (local to this user, recommended)
    /etc/kegbot/local_settings.py   (global to all users, requires root access)

  If in doubt, use the default.
  """
  FLAG = 'settings_file'

  def validate(self, ctx):
    self.value = os.path.expanduser(self.value)
    if os.path.exists(self.value):
      raise ValueError('Settings file "%s" already exists.' % self.value)
    super(SettingsPath, self).validate(ctx)

  def apply(self, ctx):
    if os.path.exists(self.value):
      raise FatalError('Settings file "%s" already exists.' % self.value)
    dirname = os.path.dirname(self.value)
    if dirname and not os.path.isdir(dirname):
      try:
        os.makedirs(dirname)
      except OSError, e:
        raise FatalError("Couldn't create settings dir '%s': %s" % (dirname, e))


class KegbotDataRoot(ConfigurationSetupStep):
  """Path to Kegbot's data root.

  This should be a directory on your filesystem where Kegbot will create its
  STATIC_ROOT (static files used by the web server, such as css and java script)
  and MEDIA_ROOT (media uploads like user profile pictures).
  """
  FLAG = 'data_root'

  def validate(self, ctx):
    self.value = os.path.expanduser(self.value)
    if os.path.exists(self.value):
      if os.listdir(self.value):
        raise ValueError('Path "%s" already exists and is not empty.' % self.value)
    super(KegbotDataRoot, self).validate(ctx)

  def apply(self, ctx):
    try:
      if not os.path.isdir(self.value):
        os.makedirs(self.value)
      os.makedirs(os.path.join(self.value, 'media'))
      os.makedirs(os.path.join(self.value, 'static'))
    except OSError, e:
      raise FatalError('Could not create directory "%s": %s' % (self.value, e))
    super(KegbotDataRoot, self).apply(ctx)

  def add_to_settings(self, ctx, outfd):
    outfd.write("MEDIA_ROOT = '%s'\n" % (os.path.join(self.value, 'media')))
    outfd.write("STATIC_ROOT = '%s'\n" % (os.path.join(self.value, 'static')))
    outfd.write("\n")


class DatabaseChoice(ConfigurationSetupStep):
  """Select database for Kegbot Server backend.

  Currently only sqlite and MySQL are supported by the setup wizard.
  """
  FLAG = 'db_type'
  CHOICES = ['sqlite', 'mysql']

class ConfigureDatabase(ConfigurationSetupStep):
  def db_type(self, ctx):
    return ctx[DatabaseChoice]

  def get_from_flag(self, ctx):
    if self.db_type(ctx) == 'sqlite':
      return FLAGS.sqlite_file
    else:
      return (FLAGS.mysql_user, FLAGS.mysql_password, FLAGS.mysql_database)

  def get_from_prompt(self, ctx):
    if self.db_type(ctx) == 'sqlite':
      default = FLAGS.sqlite_file
      val = self.do_prompt('SQLite database file within Kegbot data root', default=default)
      return os.path.join(ctx[KegbotDataRoot], val)
    else:
      user = self.do_prompt('MySQL user')
      password = getpass.getpass()
      database = self.do_prompt('Database name', default='kegbot')
      return (user, password, database)

  def validate(self, ctx):
    if self.db_type(ctx) == 'sqlite':
      self.value = os.path.expanduser(self.value)
      if os.path.exists(self.value):
        raise ValueError('SQLite database file already exists: %s' % self.value)
    else:
      user, password, database = self.value
      if user == '':
        raise ValueError('Must give a MySQL username')
      elif database == '':
        raise ValueError('Must give a MySQL database name')
    super(ConfigureDatabase, self).validate(ctx)

  def add_to_settings(self, ctx, outfd):
    if self.db_type(ctx) == 'sqlite':
      cfg = {
        'default': {
          'ENGINE': 'django.db.backends.sqlite3',
          'NAME': self.value,
        }
      }
    else:
      user, password, database = self.value
      cfg = {
        'default': {
          'ENGINE': 'django.db.backends.mysql',
          'NAME': database,
          'USER': user,
          'PASSWORD': password,
          'OPTIONS': {
            'init_command': 'SET storage_engine=INNODB',
          }
        }
      }

    outfd.write('DATABASES = ')
    pprint.pprint(cfg, stream=outfd, indent=2)
    outfd.write('\n')


STEPS = [
    RequiredLibraries(),
    SettingsPath(),
    KegbotDataRoot(),
    DatabaseChoice(),
    ConfigureDatabase(),
]


class SetupApp(app.App):
  def _Setup(self):
    app.App._Setup(self)

  def _SetupSignalHandlers(self):
    pass

  def _MainLoop(self):
    steps = STEPS
    ctx = {}

    if FLAGS.interactive:
      self.build_interactive(ctx)
    else:
      self.build(ctx)

    print ''
    print 'Applying configuration...'
    for step in steps:
      step.apply(ctx)

    settings_file = ctx[SettingsPath]
    print 'Writing settings to %s' % settings_file

    outfd = open(settings_file, 'w+')
    outfd.write(SETTINGS_TEMPLATE)
    for step in steps:
      step.add_to_settings(ctx, outfd)
    outfd.close()

    self.finish_setup()

  def build(self, ctx):
    for step in STEPS:
      try:
        step.get(interactive=False, ctx=ctx)
        step.validate(ctx)
        step.save(ctx)
      except (ValueError, FatalError), e:
        print 'ERROR: %s' % e
        sys.exit(1)

  def build_interactive(self, ctx):
    try:
      import readline
    except ImportError:
      pass

    for step in STEPS:
      while not self._do_quit:
        try:
          step.get(interactive=True, ctx=ctx)
          step.validate(ctx)
          step.save(ctx)
          print ''
          print ''
          #self._logger.info('Got value: %s' % value)
          break
        except KeyboardInterrupt, e:
          print ''
          sys.exit(1)
        except FatalError, e:
          print ''
          print 'ERROR: %s' % e
          sys.exit(1)
        except ValueError, e:
          print ''
          print ''
          print ''
          print 'ERROR: %s' % e


  def finish_setup(self):
    print 'Finishing setup ...'
    self.run_command('kegbot-admin.py syncdb --all --noinput -v 0')
    self.run_command('kegbot-admin.py migrate --all --fake --noinput -v 0')
    self.run_command('kegbot-admin.py kb_set_defaults --force')

    if FLAGS.interactive:
      self.run_command('kegbot-admin.py collectstatic')
      self.run_command('kegbot-admin.py createsuperuser')
    else:
      self.run_command('kegbot-admin.py collectstatic --noinput')
      print ''
      print 'Running non-interactively, not creating super user account.'
      print 'To finish, run: '
      print '  kegbot-admin.py createsuperuser'

    print ''
    print 'Done!'
    print ''
    print 'You may now run the dev server:'
    print 'kegbot-admin.py runserver 0.0.0.0:8000'

  def run_command(self, s):
    print 'Running command: %s' % s
    ret = subprocess.call(s.split())
    if ret != 0:
      raise ValueError('Command returned non-zero exit status (%s)' % ret)

if __name__ == '__main__':
  SetupApp.BuildAndRun(name='kegbot-setup')
