import os

print("Current directory:", os.getcwd())
print("Files in current dir:", os.listdir("."))
print("Static exists:", os.path.exists("static"))
if os.path.exists("static"):
    print("Static files:", os.listdir("static"))
