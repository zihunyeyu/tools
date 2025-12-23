from random import choice

investigator_dict = {
    'Guardian': ['Carolyn Fern', 'Carson Sinclair', 'Daniela Reyes', 'Leo Anderson', 'Mark Harrigan', 'Nathaniel Cho', 'Roland Banks', 'Sister Mary', 'Tommy Muldoon', 'Zoey Samaras'],
    'Seeker': ['Amanda Sharpe', 'Daisy Walker', 'Harvey Walters', 'Joe Diamond', 'Mandy Thompson', 'Minh Thi Phan', 'Norman Withers', 'Rex Murphy', 'Ursula Downs', 'Vincent Lee'],
    'Mystic': ['Agnes Baker', 'Akachi Onyele', 'Amina Zidane', 'Dexter Drake', 'Diana Stanley', 'Father Mateo', 'Jacqueline Fine', 'Jim Culver', 'Lily Chen', 'Luke Robinson', 'Marie Lambeau'],
    'Rogue': ['Finn Edwards', 'Jenny Barnes', 'Kymani Jones', 'Monterey Jack', 'Preston Fairmont', 'Sefina Rousseau', "\"Skids\" O'Toole", 'Tony Morgan', 'Trish Scarborough', 'Winifred Habbamock'],
    'Survivor': ['"Ashcan" Pete', 'Bob Jenkins', 'Calvin Wright', 'Darrell Simmons', 'Patrice Hathaway', 'Rita Young', 'Silas Marsh', 'Stella Clark', 'Wendy Adams', 'William Yorick'],
    'Neutral': ['Charlie Kane', 'Lola Hayes'],
}

def main():
    investigator_list = []
    for value in investigator_dict.values():
        investigator_list += value

    # print(investigator_list)
    random_list = []
    for i in range(3):
        randoms = []
        for _ in range(8):
            randoms.append(investigator_list.pop(choice(range(len(investigator_list)))))
        # print(randoms)
        random_list.append(randoms)

    selection_1 = input("请输入%d-%d的数字:" % (1, len(random_list)))
    selection_1_ = random_list[int(selection_1)-1]
    selection_2 = input("请输入%d-%d的数字:" % (1, len(selection_1_)))
    investigator = selection_1_[int(selection_2)-1]
    for key, value in investigator_dict.items():
        if investigator in value:
            print("你抽取了 %s 的 %s" % (key, investigator))

if __name__ == '__main__':
    main()