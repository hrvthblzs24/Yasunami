
import requests
#function to call a list of games based on user input and returns the gameID from the json response.
def listGames(title):
    #API call for the list of games
    urlList = "https://www.cheapshark.com/api/1.0/games?title={}".format(title)
    response = requests.get(urlList)
    data = response.json()
    
    i=1 #Counter for the # of games
    for game in data: #Start of the for loop to iterate through the data and print out every game that is close to the users search
        print(f"{i}. {game['external']}")
        i += 1
    #We give the user the choice to pick by integer.
    choice = int(input("Please pick the game you would like to view (#):")) 
    final = data[choice-1] #users final choice, since index starts at 0 we adjust the choice by -1 for the program to choose the correct game.  
    print(f"\nYour Choice: {final['external']}")
    
    #Assigning the finals users choice gameID and returning it.
    gameID = final['gameID'] 
    return gameID

def dealLook(gameID):
#function to take gameID and display the stores currently offering deals for that game.
    #API call for the Game Lookup
    urlDeals = "https://www.cheapshark.com/api/1.0/games?id={}".format(gameID)
    response = requests.get(urlDeals)
    deals = response.json()['deals']
    info = response.json()['info'] #to access the 'info' portion of the json
    #print(info)
    
    #API call for the Stores Info
    urlStore = "https://www.cheapshark.com/api/1.0/stores"
    storeResponse= requests.get(urlStore)
    stores = storeResponse.json()
    #print(stores)
    
    #Displaying the current stores that offer a deal for the users choice. By using both APIs we can compare if the storeIDs and the store name match.
    print(f"These are currently the stores selling: {info['title']}\n")
    idS =[]
    prices =[]
    for store in deals:
        price = store['price']
        storeID = store['storeID'] #setting the storeID in the deals section of the deals API to the variable storeID.
        for names in stores: #accessing the list of stores in the store url and checking if the storeID and store name match.
            if names['storeID'] == storeID:
                storeID = names['storeName']
                idS.append(storeID)
                prices.append(price)
                print(f"Store: {storeID},") 
                print(f"Current Price: ${store['price']}, Retail Price: ${store['retailPrice']}\n")
    return idS, prices
#Main
if __name__ == "__main__":
    prompt = input("Enter a video game title:")
    
    findGame = listGames(prompt)
    #print(f"GameID: {findGame}")
    
    storeNames, gamePrices = dealLook(findGame)
    print(f"Store Names: {storeNames}")
    print(f"Prices: {gamePrices}")
    
    
    
    
    
    
    