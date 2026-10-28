from cyclopts import App

app = App()

@app.command
def run():
    # read input file 
    print("hellow world!")
    pass 

if __name__ == "__main__":
    app()