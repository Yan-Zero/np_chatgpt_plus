from setuptools import setup, find_packages

setup(
    name="np_chatgpt_plus",
    version="1.2.0",
    author="Yan",
    author_email="1964649083@qq.com",
    description="A Chatbot Framework for Nonebot2",
    python_requires=">=3.11",
    keywords=["nonebot"],
    packages=find_packages(include=("np_chatgpt_plus*")),
    include_package_data=True,
    install_requires=[
        "nonebot2",
        "revChatGPT",
    ],
    license="Apache-2.0 License",
    classifiers=[
        "Framework :: AsyncIO",
        "Operating System :: OS Independent",
        "License :: OSI Approved :: Apache Software License 2.0 (Apache-2.0 License)",
        "Programming Language :: Python",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: Implementation :: CPython",
    ],
)
