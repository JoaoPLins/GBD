# Entry point for running the game.

from game import Game


def main() -> None:
    # Create and run the game app.
    
    # TODO: load configs
    print("main gameloopstarter")
    gameStatus = 2
    while gameStatus != 0:
        if gameStatus == 3:
            game.run()
            game.draw()

        elif gameStatus == 2:
            print("game loading")
            game = Game()
            gameStatus = 3

        elif gameStatus == 1:
            print("game menu")
            
        else:
            print("game quit")
            gameStatus = 0
    



if __name__ == "__main__":
    main()

