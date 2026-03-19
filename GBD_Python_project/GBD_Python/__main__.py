# TODO: Update the main function to your needs or remove it.
import pygame


def main() -> None:
    #for now this is how it is going to work. need to add a config for the screen size and other settings
    screen = pygame.display.set_mode((800, 600))
    pygame.display.set_caption("GBD")

    #main game loop is here
    print("main gameloopstarter")
    gameStatus = 2
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

