from setuptools import setup, find_packages

# optionally depends on pybase64

setup(
    name="sipyco",
    version="1.10",
    author="M-Labs",
    url="https://m-labs.hk/artiq",
    description="Simple Python communications",
    license="LGPLv3+",
    install_requires=[
        "numpy",
    ],
    packages=find_packages(),
    entry_points={
        "console_scripts": [
            "sipyco_rpctool = sipyco.sipyco_rpctool:main",
        ]
    },
)
