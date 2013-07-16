from distutils.cmd import Command
from distutils.core import setup


class TestCommand(Command):
    user_options = []

    def initialize_options(self):
        pass

    def finalize_options(self):
        pass

    def run(self):
        import sys, subprocess

        raise SystemExit(
            subprocess.call([sys.executable,
                             '-m',
                             'pisces.test']))


setup(
    name='pisces',
    version='0.0.2',
    packages=['pisces'],
    url='https://github.com/justinabrahms/pisces',
    license='MIT',
    author='Justin Abrahms',
    author_email='justin@abrah.ms',
    description='A testable python web framework',
    requires=['werkzeug'],
    cmdclass={
        'test': TestCommand
    }
)
