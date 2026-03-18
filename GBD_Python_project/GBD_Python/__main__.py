# TODO: Update the main function to your needs or remove it.



def main() -> None:
    print("main gameloopstarter")
    gameStatus = 1
    while gameStatus != 0:
        if gameStatus == 2:
            print("game running")
        elif gameStatus == 1:
            print("game menu")
        else:
            print("game quit")
            gameStatus = 0
        


if __name__ == "__main__":
    main()

