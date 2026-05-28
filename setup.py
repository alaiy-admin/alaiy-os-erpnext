from setuptools import setup, find_packages

with open("requirements.txt") as f:
    install_requires = f.read().strip().split("\n")

setup(
    name="alaiy_os_erpnext",
    version="0.0.1",
    description="alaiy OS — ERPNext custom app with Amazon SP API + Shopify GraphQL connectors",
    author="alaiy",
    author_email="pradyun@alaiy.com",
    packages=find_packages(),
    zip_safe=False,
    include_package_data=True,
    install_requires=install_requires,
)
