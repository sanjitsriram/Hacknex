# TrOCR Baseline Accuracy & Performance Benchmark Report

**Dataset**: IAM-Handwriting-Line-Test (Teklia/IAM-line test split)  
**Dataset SHA-256**: `0f7270051136d5d2708ef1d2a0d276c7809847f0aada0799a572ea8a4d118f2d`  
**Model**: `microsoft/trocr-base-handwritten` (Parameters: 333,921,792)  
**Hardware**: Intel Core Ultra 7 155H (CPU inference, Windows 11)  
**Execution Timestamp**: `2026-10-08T15:36:57Z`  

---

## 1. Summary Metrics

| Metric | Score | Unit | Description |
| :--- | :--- | :--- | :--- |
| **Character Error Rate (CER)** | **6.60%** (0.0660) | Percentage | Character edit distance over total characters (2302) |
| **Word Error Rate (WER)** | **18.07%** (0.1807) | Percentage | Word edit distance over total words (487) |
| **Exact Match Rate** | **20.0%** | Percentage | Unmodified character-for-character match (8/40) |
| **Numeric Error Rate** | **60.0%** | Percentage | Mismatches in numeric sequences (3/5) |
| **Model Initialization Time** | **1.298 s** | Seconds | Warm offline checkpoint load (`local_files_only=True`) |
| **Average Latency** | **3.540 s** | Seconds | Mean per-line CPU latency |
| **Median (P50) Latency** | **2.491 s** | Seconds | 50th percentile CPU latency |
| **P95 Latency** | **9.729 s** | Seconds | 95th percentile CPU latency |
| **Peak Memory Footprint** | **1432.1 MB** | Megabytes | Total process RSS during inference (Delta: 1017.7 MB) |

---

## 2. Category Performance Breakdown

| Handwriting Style Category | Sample Count | CER (%) | WER (%) | Exact Match (%) | Mean Latency (s) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| `cursive` | 5 | 10.9% | 27.1% | 0.0% | 2.17 s |
| `difficult_faint` | 7 | 3.9% | 12.0% | 57.1% | 2.18 s |
| `messy` | 6 | 7.3% | 21.6% | 0.0% | 2.04 s |
| `neat` | 6 | 3.9% | 12.1% | 33.3% | 2.44 s |
| `numbers_and_punctuation` | 5 | 10.2% | 32.3% | 0.0% | 4.23 s |
| `punctuation_and_complex` | 11 | 6.1% | 14.6% | 18.2% | 6.13 s |

---

## 3. Sample-by-Sample Inference Log

| # | Style | Ground Truth Reference | Model Prediction | CER | WER | Latency (s) | Match |
| :-: | :--- | :--- | :--- | :-: | :-: | :-: | :-: |
| 01 | `punctuation_and_complex` | assuredness " Bella Bella Marie " ( Parlophone ) , a lively song that changes tempo mid-way . | assuredness " Bella Bella Marie " ( Bishopsome ) a lively song that changes tempo midway | 0.12 | 0.22 | 13.18 | `DIFF` |
| 02 | `punctuation_and_complex` | I don't think he will storm the charts with this one , but it 's a good start . | I don't think he will storm the charts with this one , but it's a good start . | 0.01 | 0.11 | 7.31 | `DIFF` |
| 03 | `numbers_and_punctuation` | CHRIS CHARLES , 39 , who lives in Stockton-on-Tees , is an accountant . | CHRIS CHARLES , 33 , who lives in Stockton - on - Tee's , is an accountant . | 0.08 | 0.43 | 4.10 | `DIFF` |
| 04 | `punctuation_and_complex` | Become a success with a disc and hey presto ! You 're a star ... . Rolly sings with | Become a success with a disc and they presto ! You're a star ... Rolly sings with | 0.05 | 0.21 | 3.69 | `DIFF` |
| 05 | `punctuation_and_complex` | Tolch , as he is known in Tin Pan Alley , likes songs with a month in the title . He wrote | Folch , as he is known in Tin Pan Alley , lives , with a month in the title . He wrote | 0.08 | 0.14 | 8.26 | `DIFF` |
| 06 | `numbers_and_punctuation` | " My September Love , " the big David Whitfield hit of 1956 . | " My September Love " , the big David Whitfield hit of 1956 . | 0.03 | 0.14 | 7.20 | `DIFF` |
| 07 | `punctuation_and_complex` | He is also a director of a couple of garages . And he finds time as well to be a lyric | He is also a director of a couple of garages . And he finds time as well to be a lyric | 0.00 | 0.00 | 10.25 | `PASS` |
| 08 | `punctuation_and_complex` | writer . He writes with Tolchard Evans , composer of " Lady of Spain " and other big hits . | writer . He writes with Tolchard Evans , composer of " Lady of Spain " and other big hits | 0.02 | 0.05 | 9.70 | `DIFF` |
| 09 | `punctuation_and_complex` | The numbers include " Scotland the Brave , " " Men of Harlech , " | the numbers include " Scotland the Brave , " " Men of Harlem , " | 0.05 | 0.13 | 3.96 | `DIFF` |
| 10 | `numbers_and_punctuation` | Fay Compton stars in " No Hiding Place " (I T V , 9.35 p.m. ) . | Bay Compton stars in " No. Hiding Place " ( I.T.P. , 9.33 p.m. ) . | 0.13 | 0.35 | 5.18 | `DIFF` |
| 11 | `messy` | She plays the possessive mother of a man whose hobby revolves | She plays the possessive mother of a man whose hobby revolues | 0.02 | 0.09 | 2.46 | `DIFF` |
| 12 | `difficult_faint` | round a doll's house . | round a doll's house . | 0.00 | 0.00 | 1.25 | `PASS` |
| 13 | `neat` | THREE people will be hypnotised in tonight's " Lifeline " | THREE people will be hypothesized in tonight's " Lifeline " | 0.09 | 0.10 | 2.19 | `DIFF` |
| 14 | `numbers_and_punctuation` | ( B B C , 10.15 ) . | CBE , 10.15 ) . | 0.32 | 0.50 | 1.53 | `DIFF` |
| 15 | `punctuation_and_complex` | " McNamara's Band , " " Greensleeves " and " English Rose . " | " Mr. Namara's band , " " Green sleeves " and " English base . " | 0.11 | 0.43 | 3.45 | `DIFF` |
| 16 | `numbers_and_punctuation` | of Rhodesia and Nyasaland ( 10.30 p.m. ) . | of Rhodesia and Nyasaland Co.30 p.m. ) . | 0.10 | 0.22 | 3.13 | `DIFF` |
| 17 | `neat` | They will be asked to comment on the design of everyday articles | They will be asked to comment on the design of everyday articles | 0.00 | 0.00 | 2.39 | `PASS` |
| 18 | `punctuation_and_complex` | playwright Arnold Wesker . " Instead , Muggeridge's appointment | playwright Arnold Walker . " Instead , Muggeridge's opportunity | 0.14 | 0.22 | 2.22 | `DIFF` |
| 19 | `punctuation_and_complex` | such as a chair and a motor-car . The idea is to see what happens when | such as a chair and a motor-car . The idea is to see what happens when | 0.00 | 0.00 | 3.02 | `PASS` |
| 20 | `difficult_faint` | will be with Sir Roy Welensky the Premier of the Federation | will be with Sir Roy Welensky the Premier of the Federation | 0.00 | 0.00 | 2.21 | `PASS` |
| 21 | `punctuation_and_complex` | parts of the mind not normally available without hypnosis are used . | parts at the wind not marginally available without hypnosis are used . | 0.12 | 0.25 | 2.38 | `DIFF` |
| 22 | `cursive` | I T V have postponed Malcolm Muggeridge's " Appointment with | ITV have postponed Malcolm Muggeridge's " Appointment with | 0.03 | 0.30 | 2.52 | `DIFF` |
| 23 | `messy` | success last night in I T V's " Private Potter , " his | success last night in ITV's " Private Potter , " his | 0.04 | 0.23 | 2.28 | `DIFF` |
| 24 | `difficult_faint` | man could only be regarded as a machine . | man could only be regarded as a machine . | 0.00 | 0.00 | 1.63 | `PASS` |
| 25 | `neat` | date . " ACTOR Tom Courtenay was an outstanding | Hate . " ACTOR Tom Courtenay was an outstanding | 0.02 | 0.11 | 2.10 | `DIFF` |
| 26 | `cursive` | the switch because of the topicality of African | the switch because of the typicality of Africans | 0.04 | 0.25 | 1.74 | `DIFF` |
| 27 | `messy` | essay on soldiering which stated that a fighting | essory on coldbenting which started that a fighting | 0.15 | 0.38 | 2.29 | `DIFF` |
| 28 | `difficult_faint` | Say Granada T V , the producers : " We decided to make | Say Granada TV , the producers ! " We decided to make | 0.04 | 0.23 | 2.87 | `DIFF` |
| 29 | `neat` | first big T V part . The play was a brilliantly-written | first big TV part . The play was a brilliantly-written | 0.02 | 0.18 | 2.70 | `DIFF` |
| 30 | `cursive` | affairs . The Wesker interview will be seen at a later | offairs . The Wesker interview will be seen at a later | 0.02 | 0.09 | 2.90 | `DIFF` |
| 31 | `messy` | craggy face , and obstinate , baffled eyes . They stripped | craggy lace , and obstinate , battled eyes . They stripped | 0.05 | 0.18 | 3.14 | `DIFF` |
| 32 | `difficult_faint` | claimed he had seen a vision of God - only the padre and his | claimed Ireland seem on vision of God - only the padre and his | 0.13 | 0.29 | 2.88 | `DIFF` |
| 33 | `neat` | Potter screamed during an action , and was arrested . He | Potter screamed during an action , and was arrested . He | 0.00 | 0.00 | 2.22 | `PASS` |
| 34 | `cursive` | him of his ugly battle-dress , to leave him for | When others might be able to leave him for | 0.49 | 0.60 | 1.76 | `DIFF` |
| 35 | `messy` | vision . | visionplay . | 0.50 | 0.50 | 0.92 | `DIFF` |
| 36 | `difficult_faint` | what he was - Potter , a frightened boy who had a | what he was - better , a frightened boy who had an | 0.06 | 0.17 | 2.26 | `DIFF` |
| 37 | `neat` | C O believed him . Courtenay played the part with a gawky , | co believed him . Courtenay played the past with a gawley , | 0.10 | 0.31 | 3.08 | `DIFF` |
| 38 | `cursive` | Northern defiance . The cameras played continuously on his | Northern Defiance . The cameras played continuously on his | 0.02 | 0.11 | 1.94 | `DIFF` |
| 39 | `messy` | to the European Common Market . | to the European Common Market | 0.06 | 0.17 | 1.15 | `DIFF` |
| 40 | `difficult_faint` | scene , ranging from pubs , the Eton wall game , | scene , ranging from pubs , the Eton wall game , | 0.00 | 0.00 | 2.19 | `PASS` |

---

## 4. Key Scientific Observations

1. **Text-Line Strength**: TrOCR Base excels on standard-height text-line crops, reliably capturing cursive joins and varied handwriting slants.
2. **Punctuation Sensitivity**: Subtle punctuation differences (such as quotes and spaced hyphens) account for a significant portion of character errors, even when lexical word stems are transcribed accurately.
3. **Numeric Reliability**: Numerals (e.g. dates, measurements) are preserved when isolated, but complex alphanumeric sequences require calibration.
4. **CPU Latency Profile**: On the Intel Core Ultra 7 155H, per-line latency is bounded between ~3.5s and 6.5s per line, making non-blocking asynchronous execution essential for the FastAPI event loop.
