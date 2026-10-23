import csv
_rows = list(csv.reader(open('/home/claude/avenrow_master_catalog_v45.csv')))[1:]
URL = {i: r[1] for i, r in enumerate(_rows)}
LID = {i: r[0] for i, r in enumerate(_rows)}
def img(i, n):
    return _rows[i][7 + n]
NAME = {0:"Good Morning",1:"Happy Birthday",2:"Good Vibes Only",3:"Self Care Club",4:"BOO!",5:"Haunted House",6:"Trick or Treat",
7:"Ghostly Hours",8:"Midnight Magic",9:"Pumpkin Season",10:"Spooky Season",11:"Witching Hour",12:"Slow Sunday",13:"Stay Cozy",
14:"Funny Graduation",15:"New Job",16:"Funny Mom",17:"Funny Dad",18:"Funny Sibling",19:"Funny Pet Lover",20:"New Parents",21:"Funny Retirement",
22:"Teacher Appreciation",23:"Coworker Leaving",24:"Funny Birthday (Unreasonable)",25:"Housewarming",26:"Funny Birthday (Same You, New Number)",
27:"Engagement",28:"Promotion",29:"Relaxation (No Rush)",30:"Good Luck",31:"Halloween Couples",32:"Bad Decisions",33:"Ghosts Can Wait",
34:"New Home",35:"Funny Coworker",36:"Funny Birthday (Older, Wiser)",37:"Anniversary",38:"Self Care (Quiet Evening)",39:"Cancelled Plans",
40:"Couples",41:"Funny Introvert",42:"Long Distance Friendship",43:"Funny Friendship"}
B_H = "Halloween Decor & Spooky Season Ideas"; B_C = "Cozy Home & Apartment Ideas"; B_G = "Gift Ideas for Every Occasion"
B_S = "Self Care & Cozy Living"; B_F = "Gifts for Her"; B_A = "Apartment Decor Ideas"; B_K = "Candles & Candle Decor"
