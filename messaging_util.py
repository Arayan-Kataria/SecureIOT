import random

LARGE_PRIME = 105341
RAND_LIMIT = 500000

def parse_message(msg):
    if ":" not in msg:
        return None
    
    x = []

    c = msg.split(":",1)
    x.append(c[0])

    args = c[1].split(",")
    for arg in args:
        x.append(arg)

    return x

def get_diffie_nums():
    secret_num = long(random.randint(0,RAND_LIMIT))
    raisedRand = long(pow(long(3),secret_num))
    moddedRand = long(raisedRand  % long(LARGE_PRIME))
    return (secret_num,str(moddedRand))



def set_seq_num(my_secret_num,others_public_num):
    global seq_num

    try:
        received_long = long(others_public_num)
        raised_long = pow(received_long,my_secret_num)
        return raised_long % long(LARGE_PRIME)
    except ValueError:
        print("Erroneous Sequence Number Sent")
    return None