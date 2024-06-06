from setuptools import setup, find_packages

# Depends on numpy and optionally pybase64

setup(
    name="sipyco",
    version="1.7",
    author="M-Labs",
    url="https://m-labs.hk/artiq",
    description="Simple Python communications",
    license="LGPLv3+",
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "sipyco_rpctool = sipyco.sipyco_rpctool:main",
        ]
    },
)
