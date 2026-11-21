"""Conservative, source-preserving review for the original vocabulary table.

This is a presentation layer, not a lemmatizer: attested word forms and full
expressions remain visible. Raw extraction data and the optional dictionaries
are never mutated. Arabic pronunciation is a learner approximation.
"""
from __future__ import annotations

from copy import deepcopy
import re
import unicodedata


def text_key(value: str) -> str:
    value = unicodedata.normalize("NFC", value).casefold()
    value = re.sub(r"[\u0301\u064b-\u065f\u0670ـ]", "", value)
    value = value.translate(str.maketrans({"ۆ":"و", "ک":"ك", "ی":"ي"}))
    return re.sub(r"\s+", " ", value).strip(" .!?؟…،؛")


def alternatives(value: str) -> list[str]:
    """Slashes inside register labels are not alternative words."""
    parts, start, depth = [], 0, 0
    for i, char in enumerate(value):
        if char == "(":
            depth += 1
        elif char == ")":
            depth = max(0, depth - 1)
        elif char == "/" and depth == 0:
            parts.append(value[start:i].strip())
            start = i + 1
    parts.append(value[start:].strip())
    return [p for p in parts if p]


def compact(value: str) -> str:
    seen, parts = set(), []
    for part in alternatives(value):
        part = part.replace("ۆ", "و").replace("ک", "ك").replace("ی", "ي")
        identity = text_key(part)
        if identity and identity not in seen:
            seen.add(identity)
            parts.append(part)
    return " / ".join(parts)


# Content-specific corrections, deliberately separate from extraction prompts.
# Each entry is Russian -> (Arabic pronunciation, Arabic meaning, English).
# Empty fields mean retain the existing field, not erase it.
REVIEWED = {
    "добрый день": ("دُوبْرِي دْيِنْ", "نهار سعيد / مرحبًا", "Good afternoon / Good day"),
    "доброе утро": ("دُوبْرَيِه أُوتْرَ", "صباح الخير", "Good morning"),
    "добрый вечер": ("دُوبْرِي ڤْيِتْشِرْ", "مساء الخير", "Good evening"),
    "привет": ("پْرِڤْيِتْ", "مرحبًا (غير رسمي)", "Hi / Hello (informal)"),
    "здравствуйте": ("زْدْرَاسْتْڤُويْتِه", "مرحبًا (رسمي)", "Hello (formal)"),
    "до свидания": ("دَ سْڤِدَانِيَ", "إلى اللقاء", "Goodbye"),
    "пока": ("پَكَا", "إلى اللقاء (غير رسمي)", "Bye (informal)"),
    "до завтра": ("دَ زَافْتْرَ", "أراك غدًا", "See you tomorrow"),
    "спасибо": ("سْپَسِيبَ", "شكرًا", "Thank you"),
    "пожалуйста": ("پَژَالُسْتَ", "من فضلك / تفضل / عفوًا (ردًا على الشكر)", "Please / Here you are / You're welcome"),
    "извините": ("إِزْڤِنِيتِه", "المعذرة / آسف (رسمي أو جمع)", "Excuse me / Sorry (formal or plural)"),
    "читайте": ("تْشِتَايْتِه", "اقرؤوا / اقرأ بصيغة الاحترام", "Read (plural or formal)"),
    "читай": ("تْشِتَايْ", "اقرأ (للمفرد)", "Read (singular informal)"),
    "читайте, пожалуйста": ("تْشِتَايْتِه پَژَالُسْتَ", "اقرؤوا من فضلكم / اقرأ من فضلك بصيغة الاحترام", "Read, please (plural or formal)"),
    "пишете": ("پِيشِتِه", "تكتبون / تكتب بصيغة الاحترام", "You write (plural or formal)"),
    "пишите": ("پِشِيتِه", "اكتبوا / اكتب بصيغة الاحترام", "Write (plural or formal)"),
    "говорите": ("گَڤَرِيتِه", "تكلموا / تكلم بصيغة الاحترام", "Speak (plural or formal)"),
    "преподаватель": ("پْرِپَدَڤَاتِلْ", "مدرس / محاضر", "Teacher / Instructor / Lecturer"),
    "учитель": ("أُتْشِيتِلْ", "معلم", "Teacher"),
    "буква": ("بُوكْڤَ", "حرف أبجدي", "Letter of the alphabet"),
    "буквы": ("بُوكْڤِي", "حروف", "Letters"),
    "русский алфавит": ("رُوسْكِي أَلْفَڤِيتْ", "الأبجدية الروسية", "Russian alphabet"),
    "алфавит": ("أَلْفَڤِيتْ", "أبجدية", "Alphabet"),
    "и краткое": ("إِي كْرَاتْكَيِه", "اسم الحرف Й (إي القصيرة)", "Name of the letter Й (short I)"),
    "твёрдый знак": ("تْڤْيُورْدِي زْنَاكْ", "العلامة الصلبة Ъ", "Hard sign Ъ"),
    "мягкий знак": ("مْيَاخْكِي زْنَاكْ", "علامة التليين Ь", "Soft sign Ь"),
    "большая": ("بَلْشَايَ", "كبيرة؛ وفي الحروف حرف كبير", "Large (feminine) / Capital (letter)"),
    "маленькая": ("مَالِنْكَيا", "صغيرة؛ وفي الحروف حرف صغير", "Small (feminine) / Lowercase (letter)"),
    "большая буква": ("بَلْشَايَ بُوكْڤَ", "حرف كبير", "Capital letter"),
    "маленькая буква": ("مَالِنْكَيا بُوكْڤَ", "حرف صغير", "Lowercase letter"),
    "домашнее задание": ("دَمَاشْنِيِي زَدَانِيِه", "واجب منزلي", "Homework"),
    "урок": ("أُرُوكْ", "درس / حصة", "Lesson / Class"),
    "диалог": ("دِيَلُوكْ", "حوار", "Dialogue"),
    "писать": ("پِسَاتْ", "أن يكتب", "To write"),
    "тетрадь": ("تِتْرَاتْ", "دفتر / كراسة", "Notebook"),
    "словарь": ("سْلَڤَارْ", "قاموس / معجم", "Dictionary / Glossary"),
    "слова": ("سْلَڤَا", "كلمات", "Words"),
    "новые слова": ("نُوڤِيِي سْلَڤَا", "كلمات جديدة", "New words"),
    "завтра": ("زَافْتْرَ", "غدًا", "Tomorrow"),
    "очень": ("أُوتْشِنْ", "جدًا / للغاية", "Very / Extremely"),
    "очень хорошо": ("أُوتْشِنْ خَرَشُو", "جيد جدًا", "Very good"),
    "вода": ("ڤَدَا", "ماء", "Water"),
    "завод": ("زَڤُوتْ", "مصنع / معمل", "Factory / Plant"),
    "рассказ": ("رَسْكَاسْ", "قصة / حكاية", "Story / Tale"),
    "друг": ("دْرُوكْ", "صديق", "Friend (male)"),
    "как вас зовут": ("كَاكْ ڤَاسْ زَڤُوتْ؟", "ما اسمك بصيغة الاحترام؟ / ما أسماؤكم؟", "What is your name? (formal or plural)"),
    "скажите, пожалуйста": ("سْكَژِيتِه پَژَالُسْتَ", "أخبروني من فضلكم / أخبرني بصيغة الاحترام", "Tell me, please (plural or formal)"),
    "матрёшка": ("مَتْرْيُوشْكَ", "دمية ماتريوشكا الروسية المتداخلة", "Russian nesting doll / Matryoshka"),
    "большой театр": ("بَلْشُويْ تِيَاتْرْ", "مسرح البولشوي", "Bolshoi Theatre"),
    "он": ("أُونْ", "هو", "He"),
    "она": ("أَنَا", "هي", "She"),
    "они": ("أَنِي", "هم / هن", "They"),
    "мы": ("مِي", "نحن", "We"),
    "вы": ("ڤِي", "أنتم / حضرتك (للاحترام)", "You (plural or formal)"),
    "ты": ("تِي", "أنت (غير رسمي)", "You (singular informal)"),
    "это": ("إِيتَ", "هذا / هذه / هؤلاء، حسب السياق", "This is / These are"),
    "мама": ("مَامَ", "أم / ماما", "Mother / Mom"),
    "папа": ("پَاپَ", "أب / بابا", "Father / Dad"),
    "нет": ("نْيِتْ", "لا / لا يوجد", "No / There is no"),
    "почта": ("پُوتْشْتَ", "بريد / مكتب بريد؛ والبريد الإلكتروني في السياق", "Mail / Post office; email in context"),
    "фото": ("فُوتَ", "صورة فوتوغرافية / صور", "Photo / Photos"),
    "ноты": ("نُوتِي", "نوتات موسيقية / تدوين موسيقي", "Musical notes / Sheet music"),
    "имя": ("إِيمْيَ", "اسم / اسم شخصي", "Name / First name"),
    "иван": ("إِڤَانْ", "إيفان (اسم مذكر)", "Ivan (male name)"),
    "моль": ("مُولْ", "عثة", "Moth"),
    "фон": ("فُونْ", "خلفية", "Background"),
    "контроль": ("كَانْتْرُولْ", "رقابة / تحقق / اختبار تقييمي، حسب السياق", "Control / Check / Assessment"),
    "множитель": ("مْنُوژِتِلْ", "عامل ضرب", "Factor / Multiplier"),
    "стоит": ("سْتُويِتْ", "يكلف / ثمنه (للمفرد)", "Costs (singular)"),
    "стоят": ("سْتُويَتْ", "تكلف / ثمنها (للجمع)", "Cost (plural)"),
    "учите": ("أُوتْشِتِه", "تدرسون مادة / تعلّمون شخصًا (جمع أو احترام)", "You study something / teach someone (plural or formal)"),
}

# One consistent learner transcription instead of accumulated contradictory
# alternatives. These are attested vocabulary/expressions, not new headwords.
PHONETICS = dict(line.split("|", 1) for line in """
сравните|سْرَڤْنِيتِه
правильно|پْرَاڤِلْنَ
неправильно|نِپْرَاڤِلْنَ
поэт|پَإِتْ
луна|لُنَا
туалет|تُوَلِتْ
собака|سَبَاكَ
здесь|زْدْيِسْ
там|تَامْ
телефон|تِلِفُونْ
русский язык|رُوسْكِي يِزِيكْ
хорошо|خَرَشُو
молодец|مَلَدْيِتْسْ
бутылка|بُتِيلْكَ
уважение|أُڤَژِينِيِه
виктор|ڤِيكْتَرْ
по телефону|پَ تِلِفُونُ
акт|أَكْتْ
плохо|پْلُوخَ
гамак|گَمَاكْ
галактика|گَلَاكْتِكَ
женский род|ژِينْسْكِي رُوتْ
озеро|أُوزِرَ
место|مْيِسْتَ
петербург|پِتِرْبُورْكْ
россия|رَسِّيَ
клуб|كْلُوپْ
иванов|إِڤَنُوفْ
существительное|سُشِّسْتْڤِيتِلْنَيِه
исключение|إِسْكْلْيُوتْشِينِيِه
повторите|پَڤْتَرِيتِه
карта|كَارْتَ
холодно|خُولَدْنَ
магний|مَاگْنِيْ
день|دْيِنْ
подруга|پَدْرُوگَ
группа|گْرُوپَّ
гитара|گِتَارَ
робот|رُوبَتْ
аппарат|أَپَرَاتْ
мой друг|مُويْ دْرُوكْ
город|گُورَتْ
меня зовут|مِنْيَا زَڤُوتْ
салат|سَلَاتْ
шоколад|شَكَلَاتْ
машина|مَشِينَ
мужчина|مُشِّينَ
шапка|شَاپْكَ
шторы|شْتُورِي
нормально|نَرْمَالْنَ
повар|پُوڤَرْ
жарко|ژَارْكَ
журнал|ژُرْنَالْ
этаж|إِتَاشْ
гараж|گَرَاشْ
жена|ژِنَا
тоже|تُوژِه
запоминаем|زَپَمِنَايِمْ
завтрак|زَافْتْرَكْ
таблица|تَبْلِيتْسَ
профессия|پْرَفِسِّيَ
стадион|سْتَدِيُونْ
журналист|ژُرْنَلِيسْتْ
расчёска|رَشُّوسْكَ
зеркало|زْيِرْكَلَ
мыло|مِيلَ
ключ|كْلْيُوتْشْ
наушники|نَأُوشْنِكِ
аудитория|أَوْدِتُورِيَ
родители|رَدِيتِلِ
хлеб|خْلْيِپْ
какая|كَكَايَ
девушка|دْيِڤُشْكَ
полка|پُولْكَ
пальто|پَلْتُو
рюкзак|رْيُگْزَاكْ
театр|تِيَاتْرْ
справа|سْپْرَاڤَ
рынок|رِينَكْ
аэропорт|أَإِرَپُورْتْ
слева|سْلْيِڤَ
аптека|أَپْتْيِكَ
вечером|ڤْيِتْشِرَمْ
солнце|سُونْتْسِه
красивая|كْرَسِيفَيا
фабрика|فَابْرِكَ
мясо|مْيَاسَ
поликлиника|پَلِكْلِينِكَ
экскурсия|إِكْسْكُورْسِيَ
письмо|پِسْمُو
нельзя|نِلْزْيَا
мороженое|مَرُوژِنَيِه
купить|كُپِيتْ
взять|ڤْزْيَاتْ
билет|بِلِتْ
деньги|دْيِنْگِ
биолог|بِيُولَكْ
кинотеатр|كِنَتِيَاتْرْ
знать|زْنَاتْ
площадь|پْلُوشَّتْ
красная площадь|كْرَاسْنَيَ پْلُوشَّتْ
статья|سْتَتْيَا
как тебя зовут|كَاكْ تِبْيَا زَڤُوتْ؟
скажи, пожалуйста|سْكَژِي پَژَالُسْتَ
дайте, пожалуйста|دَايْتِه پَژَالُسْتَ
часы|تْشِسِي
общежитие|أَپْشِّژِيتِيِه
курить|كُرِيتْ
столица|سْتَلِيتْسَ
один|أَدِينْ
джинсы|دْژِينْسِي
сахар|سَاخَرْ
у меня есть|أُ مِنْيَا يِسْتْ
говорить по-русски|گَڤَرِيتْ پَ رُوسْكِي
домохозяйка|دَمَخَزْيَايْكَ
экономист|إِكَنَمِيسْتْ
адвокат|أَدْڤَكَاتْ
полицейский|پَلِتْسِيْسْكِي
его зовут|يِڤُو زَڤُوتْ
ещё|يِشُّو
уже|أُژِه
наречие|نَرْيِتْشِيِه
никто|نِكْتُو
вещи|ڤْيِشِّي
ноутбук|نُوتْبُوكْ
санкт-петербург|سَانْكْتْ پِتِرْبُورْكْ
очень приятно|أُوتْشِنْ پْرِيَاتْنَ
отчество|أُوتْشِسْتْڤَ
здание|زْدَانِيِه
кафе|كَفِه
исторический музей|إِسْتَرِيتْشِسْكِي مُزْيِيْ
концерт|كَنْتْسِيرْتْ
пицца|پِيتْسَّ
расскажите о себе|رَسْكَژِيتِه أَ سِبْيِه
математика|مَتِمَاتِكَ
девять|دْيِڤِتْ
натуральные числа|نَتُرَالْنِيِي تْشِيسْلَ
одиннадцать|أَدِينَّتْسَتْ
двенадцать|دْڤِنَاتْسَتْ
четырнадцать|تْشِتِيرْنَتْسَتْ
пятнадцать|پِتْنَاتْسَتْ
шестнадцать|شِسْنَاتْسَتْ
девятнадцать|دِڤِتْنَاتْسَتْ
сорок|سُورَكْ
пятьдесят|پِدِسْيَاتْ
восемьдесят|ڤُوسِمْدِسِتْ
двадцать два|دْڤَاتْسَتْ دْڤَا
четыреста|تْشِتِيرِسْتَ
пятьсот|پِتْسُوتْ
семьсот|سِمْسُوتْ
восемьсот|ڤَسِمْسُوتْ
девятьсот|دِڤِتْسُوتْ
тысяча|تِيسِتْشَ
одна тысяча|أَدْنَا تِيسِتْشَ
один миллион|أَدِينْ مِلِيُونْ
прилагательные|پْرِلَگَاتِلْنِيِي
хороший|خَرُوشِي
плохой|پْلَخُويْ
окончание|أَكَنْتْشَانِيِه
ничего|نِتْشِڤُو
красивая лампа|كْرَسِيفَيا لَامْپَ
маленький город|مَالِنْكِي گُورَتْ
новое зеркало|نُوڤَيِه زْيِرْكَلَ
старое зеркало|سْتَارَيِه زْيِرْكَلَ
английский язык|أَنْگْلِيْسْكِي يِزِيكْ
китайский язык|كِتَايْسْكِي يِزِيكْ
арабский язык|أَرَاپْسْكِي يِزِيكْ
родной язык|رَدْنُويْ يِزِيكْ
""".strip().splitlines())

PHONETICS.update(dict(line.split("|", 1) for line in """
английское письмо|أَنْگْلِيْسْكَيِه پِسْمُو
красивый город|كْرَسِيفِي گُورَتْ
человек|تْشِلَڤْيِكْ
молодой человек|مَلَدُويْ تْشِلَڤْيِكْ
пожилой человек|پَژِلُويْ تْشِلَڤْيِكْ
большая семья|بَلْشَايَ سِمْيَا
большое яблоко|بَلْشُويِه يَابْلَكَ
маленькая семья|مَالِنْكَيا سِمْيَا
большой город|بَلْشُويْ گُورَتْ
почему|پَتْشِمُو؟
потому что|پَتَمُو شْتَ
арабская музыка|أَرَاپْسْكَيا مُوزِكَ
как по-русски|كَاكْ پَ رُوسْكِي؟
интересный|إِنْتِرْيِسْنِي
моя семья|مَيَا سِمْيَا
красивый|كْرَسِيفِي
красивая девушка|كْرَسِيفَيا دْيِڤُشْكَ
дорогой|دَرَگُويْ
дешёвый|دِشُوڤِي
лёгкий|لْيُوخْكِي
сильный|سِيلْنِي
грустный|گْرُوسْنِي
весёлый|ڤِسْيُولِي
результат|رِزُلْتَاتْ
ребёнок|رِبْيُونَكْ
самая красивая|سَامَيا كْرَسِيفَيا
пожилой|پَژِلُويْ
толстый|تُولْسْتِي
женщина|ژِينْشِّنَ
эрмитаж|إِرْمِتَاشْ
я не знаю|يَا نِ زْنَايُ
спорт|سْپُورْتْ
полезно|پَلْيِزْنَ
вредно|ڤْرْيِدْنَ
опера|أُوپِرَ
бананы|بَنَانِي
фиолетовый|فِيَلْيِتَڤِي
фиолетовые|فِيَلْيِتَڤِيِي
какао|كَكَاوَ
две тысячи|دْڤْيِه تِيسِتْشِ
чёрное море|تْشُورْنَيِه مُورِه
овощи|أُوڤَشِّي
вычитание|ڤِتْشِتَانِيِه
действие|دْيِيْسْتْڤِيِه
математическое действие|مَتِمَتِيتْشِسْكَيِه دْيِيْسْتْڤِيِه
разность|رَازْنَسْتْ
уменьшаемое|أُمِنْشَايِمَيِه
вычитаемое|ڤِتْشِتَايِمَيِه
понимать|پَنِمَاتْ
делать домашнее задание|دْيِلَتْ دَمَاشْنِيِي زَدَانِيِه
ничего не делаю|نِتْشِڤُو نِ دْيِلَيُ
потом|پَتُومْ
по-русски|پَ رُوسْكِي
официант|أَفِتْسِيَانْتْ
деление|دِلْيِنِيِه
произведение|پْرَإِزْڤِدْيِنِيِه
делимое|دِلِيمَيِه
делитель|دِلِيتِلْ
по-арабски|پَ أَرَاپْسْكِي
по-итальянски|پَ إِتَلْيَانْسْكِي
меньше|مْيِنْشِه
дробь|دْرُوپْ
одна четвёртая|أَدْنَا تْشِتْڤْيُورْتَيا
одна седьмая|أَدْنَا سِدْمَايَ
лето|لْيِتَ
тёплая погода|تْيُوپْلَيا پَگُودَ
замечательный|زَمِتْشَاتِلْنِي
театральная площадь|تِيَتْرَالْنَيا پْلُوشَّتْ
заниматься спортом|زَنِمَاتْسَّ سْپُورْتَمْ
тут / здесь|تُوتْ / زْدْيِسْ
аудитория / аудитории|أَوْدِتُورِيَ / أَوْدِتُورِيِ
этаж / этажи|إِتَاشْ / إِتَژِي
журнал / журналы|ژُرْنَالْ / ژُرْنَالِي
море / моря|مُورِه / مَرْيَا
яблоко / яблоки|يَابْلَكَ / يَابْلَكِ
город / города|گُورَتْ / گَرَدَا
паспорт / паспорта|پَاسْپَرْتْ / پَسْپَرْتَا
сын / сыновья|سِينْ / سِنَڤْيَا
человек / люди|تْشِلَڤْيِكْ / لْيُودِ
ребёнок / дети|رِبْيُونَكْ / دْيِتِ
спортсмен / спортсменка|سْپَرْتْسْمْيِنْ / سْپَرْتْسْمْيِنْكَ
""".strip().splitlines()))

PHONETICS.update(dict(line.split("|", 1) for line in """
восемь|ڤُوسِمْ
пять|پْيَاتْ
шесть|شْيِسْتْ
семь|سْيِمْ
десять|دْيِسِتْ
тринадцать|تْرِنَاتْسَتْ
семнадцать|سِمْنَاتْسَتْ
восемнадцать|ڤَسِمْنَاتْسَتْ
двадцать|دْڤَاتْسَتْ
тридцать|تْرِيتْسَتْ
семьдесят|سْيِمْدِسِتْ
умножить|أُمْنُوژِتْ
разделить|رَزْدِلِيتْ
согласные|سَگْلَاسْنِيِي
""".strip().splitlines()))


def final_devoicing(russian: str, pronunciation: str) -> str:
    """Only isolated words: do not impose word-final rules on connected speech."""
    if not re.fullmatch(r"[а-яё\u0301]+", russian.casefold()):
        return pronunciation
    final = text_key(russian).rstrip("ь")[-1:]
    sounds = {"б":("ب", "پ"), "в":("ڤ", "ف"), "г":("گغج", "ك"),
              "д":("د", "ت"), "ж":("ژج", "ش"), "з":("ز", "س")}
    if final not in sounds:
        return pronunciation
    voiced, unvoiced = sounds[final]
    # Replace the final consonant only if it is actually written as voiced.
    return re.sub("[" + voiced + r"](?=[\u064b-\u065f\u0670]*$)", unvoiced, pronunciation)

PHONETICS.update(dict(line.split("|", 1) for line in """
читать|تْشِتَاتْ
читаешь|تْشِتَايِشْ
пишешь|پِيشِشْ
написать|نَپِسَاتْ
слушать|سْلُوشَتْ
слушайте|سْلُوشَايْتِه
повторяете|پَڤْتَرْيَايِتِه
повторять|پَڤْتَرْيَاتْ
повторяет|پَڤْتَرْيَايِتْ
проверять|پْرَڤِرْيَاتْ
проверьте|پْرَڤْيِرْتِه
запоминайте|زَپَمِنَايْتِه
обозначать|أَبَزْنَتْشَاتْ
уменьшать|أُمِنْشَاتْ
учить|أُتْشِيتْ
учит|أُوتْشِتْ
учим|أُوتْشِمْ
учиться|أُتْشِيتْسَّ
учатся|أُوتْشَتْسَّ
учишься|أُوتْشِشْسَ
изучать|إِزُتْشَاتْ
завтракать|زَافْتْرَكَتْ
завтракаем|زَافْتْرَكَيِمْ
завтракаю|زَافْتْرَكَيُ
завтракает|زَافْتْرَكَيِتْ
завтракают|زَافْتْرَكَيُتْ
обедать|أَبْيِدَتْ
обедаем|أَبْيِدَيِمْ
обедает|أَبْيِدَيِتْ
обедаете|أَبْيِدَيِتِه
обедают|أَبْيِدَيُتْ
ужинать|أُوژِنَتْ
ужинаем|أُوژِنَيِمْ
ужинают|أُوژِنَيُتْ
готовить|گَتُوڤِتْ
пить|پِيتْ
парковать|پَرْكَڤَاتْ
бывать|بِڤَاتْ
находиться|نَخَدِيتْسَّ
находится|نَخُودِتْسَّ
находятся|نَخُودْيَتْسَّ
отправила|أَتْپْرَاڤِلَ
покупать|پَكُپَاتْ
работать|رَبُوتَتْ
работал|رَبُوتَلْ
работала|رَبُوتَلَ
работали|رَبُوتَلِ
работаешь|رَبُوتَيِشْ
отдыхать|أَتْدِخَاتْ
любить|لْيُبِيتْ
любит|لْيُوبِتْ
нравится|نْرَاڤِتْسَّ
нравятся|نْرَاڤْيَتْسَّ
начинайте|نَتْشِنَايْتِه
делать|دْيِلَتْ
делаешь|دْيِلَيِشْ
делаете|دْيِلَيِتِه
искать|إِسْكَاتْ
ищешь|إِيشِّشْ
играть|إِگْرَاتْ
гулять|گُلْيَاتْ
можете|مُوژِتِه
извини|إِزْڤِنِي
говорить|گَڤَرِيتْ
скажи|سْكَژِي
сказать|سْكَزَاتْ
разговаривать|رَزْگَڤَارِڤَتْ
понимаешь|پَنِمَايِشْ
думать|دُومَتْ
покажите|پَكَژِيتِه
позвонить|پَزْڤَنِيتْ
познакомьтесь|پَزْنَكُومْتِسْ
спрашивать|سْپْرَاشِڤَتْ
спрашиваешь|سْپْرَاشِڤَيِشْ
отвечать|أَتْڤِتْشَاتْ
ответьте|أَتْڤْيِتْتِه
рубль|رُوبْلْ
боль|بُولْ
вещь|ڤْيِشْ
водитель|ڤَدِيتِلْ
дверь|دْڤْيِرْ
дождь|دُوشْتْ
дочь|دُوتْشْ
ель|يِلْ
календарь|كَلِنْدَارْ
картофель|كَرْتُوفِلْ
конь|كُونْ
кремль|كْرْيِمْلْ
кровать|كْرَڤَاتْ
лошадь|لُوشَتْ
любовь|لْيُبُوفْ
мать|مَاتْ
мель|مْيِلْ
мечеть|مِتْشِتْ
модель|مَدْيِلْ
морковь|مَرْكُوفْ
ноль|نُولْ
ночь|نُوتْشْ
нуль|نُولْ
обь|أُوپْ
осень|أُوسِنْ
отель|أَتْيِلْ
ремень|رِمْيِنْ
севастополь|سِڤَسْتُوپَلْ
секретарь|سِكْرِتَارْ
стиль|سْتِيلْ
строитель|سْتْرَإِتِلْ
фестиваль|فِسْتِڤَالْ
церковь|تْسْيِرْكَفْ
часть|تْشَاسْتْ
числитель|تْشِسْلِيتِلْ
знаменатель|زْنَمِنَاتِلْ
январь|يِنْڤَارْ
""".strip().splitlines()))


# Checked noun senses, not an ending-based guess. Notably моль=moth is feminine,
# unlike the masculine chemical unit. Infinitives/numerals are intentionally absent.
SOFT_NOUN_GENDER = {
    **dict.fromkeys("водитель делитель день дождь знаменатель календарь картофель контроль конь кремль множитель националь ноль нуль отель преподаватель ремень родитель рубль севастополь секретарь словарь сомножитель стиль строитель учитель фестиваль числитель январь".split(), "он"),
    **dict.fromkeys("боль вещь дверь дочь дробь ель кровать лошадь любовь мать мель мечеть модель моль морковь ночь обь осень площадь разность соль тетрадь церковь часть".split(), "она"),
    # Attested noun headwords in lecture 33, including Russian city names.
    **dict.fromkeys("корабль портфель спектакль суздаль ярославль".split(), "он"),
    **dict.fromkeys("астрахань жизнь казань крепость пермь поверхность рязань тверь".split(), "она"),
    "сибирь": "она",
    "игорь": "он",
    "степень": "она",
    "показатель": "он",
    "писатель": "он",
    "внимательность": "она",
    "корень": "он",
}


def display_russian(text: str, meaning: str = "") -> str:
    """Mark noun headwords, including nouns within attested slash groups.

    Do not insert annotations in example sentences (e.g. Добрый день), where
    they would interrupt the sentence or look like a spoken word.
    """
    output = []
    for part in alternatives(text):
        bare = text_key(part)
        gender = SOFT_NOUN_GENDER.get(bare)
        if bare == "моль" and re.search(r"\b(mole|mol|unit)\b", meaning.casefold()) and "moth" not in meaning.casefold():
            gender = "он"
        # The lecture-43 noun is feminine; the homographic verb means "to bake".
        if bare == "печь" and re.match(r"\s*(?:an?\s+)?(?:stove|oven)\b", meaning.casefold()):
            gender = "она"
        output.append(f"{part} ({gender})" if gender else part)
    return " / ".join(output)


def _meaning_match(left: str, right: str) -> bool:
    def meanings(value):
        return {re.sub(r"\([^)]*\)", "", text_key(p)).strip() for p in alternatives(value)}
    return bool(meanings(left) & meanings(right))


def _union_source(target: dict, source: dict) -> None:
    target["source_indices"] = sorted(set(target["source_indices"] + source["source_indices"]))
    target["lectures"] = sorted(set(target.get("lectures", []) + source.get("lectures", [])))
    target["legacy_sources"] = sorted(set(target.get("legacy_sources", []) + source.get("legacy_sources", [])))


def review_vocabulary(records: list[dict]) -> dict:
    """Review locally without deleting any original source or inventing words."""
    entries, changes = [], []
    for index, original in enumerate(records):
        row = deepcopy(original)
        row["source_indices"] = [index]
        row["legacy_sources"] = []
        if row.get("source_note"):
            row["legacy_sources"] = [row["source_note"]]
        russian = row.get("russian", "").replace("Буكвы", "Буквы")
        row["russian"] = russian
        group = alternatives(russian)
        for field in ("arabic", "english"):
            # Position-aligned translations in a group must keep their order.
            if len(group) == 1:
                row[field] = compact(row.get(field, ""))
            else:
                row[field] = row.get(field, "").replace("ۆ", "و")
        override = REVIEWED.get(text_key(russian))
        sense_guards = {
            "моль": r"\bmoth\b",
            "стоит": r"\bcosts?\b",
            "стоят": r"\bcosts?\b",
            "учите": r"\byou\b",
            "говорите": r"^(speak|talk)(?:\b|$)",
        }
        guard = sense_guards.get(text_key(russian))
        if guard and not re.search(guard, original.get("english", ""), re.I):
            override = None
        if override:
            for field, value in zip(("pronunciation", "arabic", "english"), override):
                if value:
                    row[field] = value
            row["pronunciation_reviewed"] = True
        else:
            row["pronunciation"] = compact(row.get("pronunciation", ""))
        pronunciation = PHONETICS.get(text_key(russian))
        if not pronunciation and len(group) > 1:
            old_parts = alternatives(row.get("pronunciation", ""))
            if len(old_parts) == len(group):
                pronunciation = " / ".join(
                    PHONETICS.get(text_key(part)) or
                    (REVIEWED.get(text_key(part)) or ("",))[0] or old_parts[n]
                    for n, part in enumerate(group)
                )
        if pronunciation:
            row["pronunciation"] = pronunciation
            row["pronunciation_reviewed"] = True
        if len(group) == 1:
            row["pronunciation"] = final_devoicing(russian, row["pronunciation"])
        else:
            pronunciations = alternatives(row["pronunciation"])
            if len(pronunciations) == len(group):
                row["pronunciation"] = " / ".join(final_devoicing(part, pronunciations[n]) for n,part in enumerate(group))
        for field in ("russian", "pronunciation", "arabic", "english"):
            if row.get(field) != original.get(field):
                changes.append({"source_index":index, "field":field, "before":original.get(field), "after":row[field]})
        entries.append(row)

    # Exact spelling duplicates are merged only with a compatible meaning.
    # Marked accents remain significant so homographs cannot be conflated.
    removed = set()
    spelling_index = {}
    for i, row in enumerate(entries):
        spelling = row["russian"].casefold().strip(".!?؟")
        spelling_index.setdefault(spelling, []).append(i)
    for candidates in spelling_index.values():
        i = candidates[0]
        row = entries[i]
        for j in candidates[1:]:
            other = entries[j]
            if _meaning_match(row.get("english", ""), other.get("english", "")):
                _union_source(row, other)
                row["arabic"] = compact(row["arabic"] + " / " + other["arabic"])
                row["english"] = compact(row["english"] + " / " + other["english"])
                removed.add(j)

    # Only reviewed, position-aligned attested groups may absorb matching rows.
    # No blanket slash splitting, lemmatization or generated inflections.
    groups = sorted(range(len(entries)), key=lambda i: -len(alternatives(entries[i]["russian"])))
    for i in groups:
        row = entries[i]
        if i in removed:
            continue
        ru, ar, en = [alternatives(row.get(f, "")) for f in ("russian", "arabic", "english")]
        if len(ru) < 2 or len(ru) != len(ar) or len(ru) != len(en):
            continue
        for j, other in enumerate(entries):
            if j == i or j in removed:
                continue
            other_parts = alternatives(other["russian"])
            other_en = alternatives(other.get("english", ""))
            if len(other_parts) != 1 or len(other_en) == 0:
                continue
            for n, part in enumerate(ru):
                # Keep explicitly different accents and different meanings.
                if part.casefold() != other_parts[0].casefold():
                    continue
                if not _meaning_match(en[n], other.get("english", "")):
                    continue
                # Preserve any additional senses not represented by the group.
                if not all(_meaning_match(p, en[n]) for p in other_en):
                    continue
                _union_source(row, other)
                removed.add(j)
                break

    result = [row for i, row in enumerate(entries) if i not in removed]
    # Keep one identical/reversed synonym group, without reversing phonetics.
    by_parts = {}
    final = []
    for row in result:
        parts = alternatives(row["russian"])
        signature = tuple(sorted(p.casefold() for p in parts))
        prior = by_parts.get(signature)
        if len(parts) > 1 and prior and text_key(prior["arabic"]) == text_key(row["arabic"]):
            _union_source(prior, row)
        else:
            by_parts[signature] = row
            final.append(row)
    coverage = {i for row in final for i in row["source_indices"]}
    if coverage != set(range(len(records))):
        raise ValueError("Vocabulary source coverage failed")
    for row in final:
        row["display_russian"] = display_russian(row["russian"], row.get("english", ""))
    return {"version":1, "source_count":len(records), "row_count":len(final),
            "merged_rows":len(records)-len(final), "changes":changes, "vocabulary":final}
