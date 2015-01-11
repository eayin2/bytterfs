from distutils.core import setup
setup(
    # Application name:
    name="bytterfs",

    # Version number (initial):
    version="0.2",

    # Application author details:
    author="eayin2",
    author_email="eayin2 at gmail dot com",

    scripts=["bytterfs.py"],

    # Include additional files into the package
    include_package_data=True,

    # Details
    url="https://github.com/eayin2/bytterfs",

    #
    # license="LICENSE.txt",
    description="Backup script for btrfs send/receive.",

    # long_description=open("README.txt").read(),

    # Dependent packages (distributions)
    install_requires=[],
)
