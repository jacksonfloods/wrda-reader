#!/usr/bin/env python3
"""Build the review table of proposed corrections to the scan of WRDA 1992 (same form as review_misreads_1988.py and _1990.py).
Usage: misreads_review_1988.py STRUCTURE_DIR OUT_DIR
Reads the structure file; writes OUT_DIR/WRDA 1992 misreads to review.html and .tsv. Changes nothing else.

Each entry: (as scanned, planned fix, how sure, note). how sure: yes = plain misreading; look = my best
reading, worth your eye; page = I would read the page image before fixing."""
import collections
import csv
import html
import json
import pathlib
import re
import sys

sdir, odir = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
Y, L, P = 'yes', 'look', 'page'
FIX = [
    # ---- sec. 1(b), the contents list
    ('control prqiect. Walnut', 'control project, Walnut', Y, 'a period where the comma belongs'), ('Montgomeiv', 'Montgomery', Y, ''),
    ('M{gor', 'Major', Y, 'read from the page'), ('APPUCABLE', 'APPLICABLE', Y, ''), ('Volimtary', 'Voluntary', Y, ''),
    ('infrastructiue', 'infrastructure', Y, ''), ("'Tiffade", '"Made', Y, 'the heading of sec. 226 reads "MADE IN AMERICA"'),
    ('pn^am', 'program', Y, ''), ('Georeia', 'Georgia', Y, ''), ('Maiyland', 'Maryland', Y, ''), ('Portiigese', 'Portuguese', Y, ''),
    ('Kentuckv', 'Kentucky', Y, ''), ('expendi> tures', 'expenditures', Y, ''), ('Conemau^', 'Conemaugh', Y, ''),
    ('mitimtion', 'mitigation', Y, ''), ('Oluo', 'Ohio', Y, ''), ('Nortii', 'North', Y, ''), ('prot^tion', 'protection', Y, ''),
    ('Bufialo', 'Buffalo', Y, ''), ('Coimty', 'County', Y, ''), ('Illinois ana Michigan', 'Illinois and Michigan', Y, ''),
    ('Meadowlands area. New Jersey', 'Meadowlands area, New Jersey', Y, 'period for comma'),
    ('Availability m contaminated', 'Availability of contaminated', Y, ''),
    ('Sec. 346. Bank', 'Sec. 345. Bank', Y, 'read from the page; the scan printed 346 twice'),
    ('Sec. 506. State', 'Sec. 505. State', Y, 'read from the page; the scan printed 506 twice'),
    ('Sec. 610.', 'Sec. 510.', Y, 'read from the page'),
    # ---- sec. 2, findings
    ('mimicipal', 'municipal', Y, ''), ('complementary^', 'complementary', Y, ''), ('transportetion', 'transportation', Y, ''),
    ('abilitv', 'ability', Y, ''), ('Stetes', 'States', Y, ''), ('industiy', 'industry', Y, ''), ('coste', 'costs', Y, ''),
    ('aspecte', 'aspects', Y, ''), ('serviceoriented', 'service-oriented', L, 'the print breaks it at a line end after "service-"'),
    ('mdependent', 'independent', Y, ''), ('investmente', 'investments', Y, ''), ('forei^', 'foreign', Y, ''),
    ('midti-trillion', 'multi-trillion', Y, ''), ('porte', 'ports', Y, ''), ('ite ability', 'its ability', Y, ''), ('tiie', 'the', Y, ''),
    ('protection ana enhancement', 'protection and enhancement', Y, ''),
    # ---- sec. 101
    ('navigation. Southeast Alaska', 'navigation, Southeast Alaska', Y, 'period for comma'), ('£ui estimated', 'an estimated', Y, ''),
    ('Julv', 'July', Y, ''), ('momfied', 'modified', Y, ''), ('KiSSIMMEE', 'KISSIMMEE', Y, 'small capitals read as small letters'),
    ('ecosvstem', 'ecosystem', Y, ''), ('Secretiury', 'Secretary', Y, ''),
    ('navigation. Port Everglades Harbor', 'navigation, Port Everglades Harbor', Y, 'period for comma'),
    ('navigation. Savannah', 'navigation, Savannah', Y, 'period for comma'), ('Developtment', 'Development', Y, ''),
    ('S A U G U S RIVER A N D', 'SAUGUS RIVER AND', Y, 'letter-spaced by the scan'), ('Federcd', 'Federal', Y, ''),
    ('flood control. Las Vegas', 'flood control, Las Vegas', Y, 'period for comma'), ('Jime', 'June', Y, ''),
    ('V2', '1/2', Y, 'read from the page: the print has ½'), ('Grcinde', 'Grande', Y, ''), ('totel', 'total', Y, ''),
    ('firom', 'from', Y, ''), ('witi^', 'with', Y, ''), ('flood control. Shoal Creek', 'flood control, Shoal Creek', Y, 'period for comma'),
    # ---- sec. 102
    ('l£uids', 'lands', Y, ''), ('€my', 'any', Y, ''), ('imtil', 'until', Y, ''), ('acouired', 'acquired', Y, ''), ('witn', 'with', Y, ''),
    ('GoLETA', 'GOLETA', Y, ''), ('Cioleta', 'Goleta', Y, 'the heading reads GOLETA'), ('OcEANSiDE', 'OCEANSIDE', Y, ''),
    ('Conmiittee', 'Committee', Y, ''), ('northem', 'northern', Y, ''), ('OUARE', "O'HARE", Y, "the text of the item says O'Hare"),
    ('Secretfury', 'Secretary', Y, ''), ('Heirbors', 'Harbors', Y, ''), ('materisd', 'material', Y, ''),
    ('flood protection. South Frankfort', 'flood protection, South Frankfort', Y, 'period for comma'), ('authorizea', 'authorized', Y, ''),
    ('proiect', 'project', Y, ''), ('amended l^ inserting', 'amended by inserting', Y, ''), ('canying', 'carrying', Y, ''),
    ('fi:Y)m', 'from', Y, ''), ('Secretaiy', 'Secretary', Y, ''), ('pajnnents', 'payments', Y, ''),
    ('navigation. Parish Creek', 'navigation, Parish Creek', Y, 'period for comma'), ('nrst', 'first', Y, ''), ('boundanr', 'boundary', Y, ''),
    ('BuFFUMViLLE', 'BUFFUMVILLE', Y, ''), ('Buflumville', 'Buffumville', Y, ''), ('Sout^ Fork', 'South Fork', Y, ''),
    ('Resoiirces', 'Resources', Y, ''), ('navigation. New Madrid', 'navigation, New Madrid', Y, 'period for comma'),
    ('assimie', 'assume', Y, ''), ('PAPILUON', 'PAPILLION', Y, ''), ('datea', 'dated', Y, ''), ('(aX18)', '(a)(18)', Y, ''),
    ('fiill', 'full', Y, ''), ('ajfter', 'after', Y, ''), ('proposed curts', 'proposed arts', Y, 'read from the page'),
    ('inserting shallbe undertsuken"', 'inserting "shall be undertaken"', Y, 'read from the page'), ('(CXvi)', '(C)(vi)', Y, ''),
    ('afi»r \'Yor"', 'after "for"', Y, 'read from the page'), ('appears ^ e purpose', 'appears "the purpose', Y, 'read from the page'),
    ('integrity of;', 'integrity of";', Y, 'read from the page: a closing quotation mark'), ('(CXvii)', '(C)(vii)', Y, ''),
    ("before'Wetlands", 'before "Wetlands', Y, ''), ('iniserting', 'inserting', Y, ''), ("'^y this paragraph", '"by this paragraph', Y, ''),
    ('(CXviii)', '(C)(viii)', Y, ''), ('fincmcial', 'financial', Y, ''), ('"economic .', '"economic".', Y, 'read from the page'),
    ('RARTTAN', 'RARITAN', Y, ''), ('Cliflwood', 'Cliffwood', Y, ''), ('Jersev', 'Jersey', Y, ''), ('(Jontrol', 'Control', Y, ''),
    ('fii^m', 'from', Y, ''), ('project oy that', 'project by that', Y, ''), ("Fedei'eil", 'Federal', Y, ''), ("fi'om", 'from', Y, ''),
    ('Uttoral', 'littoral', Y, ''), ('modified b^ the', 'modified by the', Y, ''), ('fiirther', 'further', Y, ''),
    ('BROKEN Bow', 'BROKEN BOW', Y, 'small capitals read as small letters'), ('Red iver', 'Red River', Y, ''), ('stora^^e', 'storage', Y, ''),
    ('nishery', 'fishery', Y, ''), ('of Uie Water', 'of the Water', Y, ''), ('imder', 'under', Y, ''), ('Secreteiy', 'Secretary', Y, ''),
    ('Roberto', 'Roberts', Y, 'the heading reads RAY ROBERTS'), ('wnere', 'where', Y, ''), ('mterior', 'interior', Y, ''),
    ('throi:^h', 'through', Y, ''), ('pipeUnes', 'pipelines', Y, ''), ('Secretsuy', 'Secretary', Y, ''), ('systerns', 'systems', Y, ''),
    ('accumiilated', 'accumulated', Y, ''),
    # ---- sec. 103
    ('£uid', 'and', Y, ''), ('naturcd', 'natural', Y, ''), ('cont£dned', 'contained', Y, ''), ('ESTABUSHMENT', 'ESTABLISHMENT', Y, ''),
    ('museimi', 'museum', Y, ''), ('Rivenront', 'Riverfront', Y, ''), ('Arm^ Corps', 'Army Corps', Y, ''), ('usmg', 'using', Y, ''),
    ('R E L A T E D', 'RELATED', Y, 'letter-spaced'),
    ('OPERATIONSRESPONSE', 'OPERATIONS-RESPONSE', L, 'the print breaks it at a line end after "OPERATIONS-"'),
    ('En^eers', 'Engineers', Y, ''), ('eiaeTgency', 'emergency', Y, ''), ('Arktmsas', 'Arkansas', Y, ''),
    # ---- secs. 104-106
    ('LOUISIANA.^A', 'LOUISIANA.—A', Y, 'read from the page; the dash was misread, so the build missed this heading and will now read it'),
    ('mdlities', 'facilities', Y, ''), ('canv', 'carry', Y, ''), ('Brodc', 'Brock', Y, 'read from the page; the heading reads BROCK'),
    ('flood control. White River', 'flood control, White River', Y, 'period for comma'),
    ('flood control. Little Fossil', 'flood control, Little Fossil', Y, 'period for comma'), ('amoimt', 'amount', Y, ''),
    ('aflecting', 'affecting', Y, ''), ('cost snaring', 'cost sharing', Y, ''), ('rights-of-wav', 'rights-of-way', Y, ''),
    ('(cX3)', '(c)(3)', Y, ''),
    # ---- sec. 107
    ('\'iien"', '"ten"', Y, 'read from the page'), ('insertmg', 'inserting', Y, ''),
    ('59-194 O--93 9 : QL 3 (Pt. 6)', '', Y, "a printer's mark at the foot of the page, not part of the act; the line is dropped"),
    ('otner', 'other', Y, ''), ('**(B) LIMITATION,', '"(B) LIMITATION.', Y, 'read from the page'), ('amoimts', 'amounts', Y, ''),
    ('(IXA)', '(1)(A)', Y, ''), ('v_ "(ii)', '"(ii)', Y, 'read from the page: a stray mark'), ('(IXB)', '(1)(B)', Y, ''),
    ('**(iii)', '"(iii)', Y, ''), ('(IXG)', '(1)(C)', Y, 'read from the page'), ('(7XA)', '(7)(A)', Y, ''), ('(aX2)', '(a)(2)', Y, ''),
    # ---- secs. 108-113
    ('A^culture', 'Agriculture', Y, ''), ('Colimibia', 'Columbia', Y, ''), ('paid VT,', 'paid 1/2', Y, 'read from the page: ½'),
    ('niimber', 'number', Y, ''),
    # ---- sec. 114
    ('detenmning', 'determining', Y, ''), ('g -ound', 'ground', Y, ''), ('tlie', 'the', Y, ''), ('resulte', 'results', Y, ''),
    ('tne', 'the', Y, ''), ('auUiorized', 'authorized', Y, ''), ('stabilitv', 'stability', Y, ''), ('Canavercd', 'Canaveral', Y, ''),
    ('ccurrjring', 'carrying', Y, ''), ('thsui', 'than', Y, ''), ('Chsumel', 'Channel', Y, ''), ('supplv', 'supply', Y, ''),
    ('Taimton', 'Taunton', Y, 'read from the page'), ('luider', 'under', Y, ''), ('pl£m', 'plan', Y, ''),
    ('Transportotion', 'Transportation', Y, ''), ('Representetives', 'Representatives', Y, ''), ('hascule', 'bascule', Y, ''),
    ('feasibiUty', 'feasibility', Y, ''), ('feasibUiW', 'feasibility', Y, ''), ('Strawberrv', 'Strawberry', Y, ''), ('stu(^', 'study', Y, ''),
    ('Strawbeny', 'Strawberry', Y, ''), ('WiSTER', 'WISTER', Y, ''), ('tJie', 'the', Y, ''), ('modiMng', 'modifying', Y, ''),
    ('a4just', 'adjust', Y, ''), ('Bav', 'Bay', Y, ''), ('CORPUS CHRISTI Smp', 'CORPUS CHRISTI SHIP', Y, ''),
    ('navigation. Corpus Christi', 'navigation, Corpus Christi', Y, 'period for comma'), ('autiiorized', 'authorized', Y, ''),
    ('Hcurbor', 'Harbor', Y, ''), ('deptn', 'depth', Y, ''), ('establishirig', 'establishing', Y, ''), ('utiUzing', 'utilizing', Y, ''),
    ('opportimities', 'opportunities', Y, ''), ('I^pecific', 'Specific', Y, ''), ('£iiter', 'after', Y, ''),
    # ---- secs. 115-118
    ('E roject', 'project', Y, ''), ('isdce Pontchartrain', 'Lake Pontchartrain', Y, ''),
    ('flood control. Green Bay', 'flood control, Green Bay', Y, 'period for comma'), ('MIS-SOURI', 'MISSOURI', Y, 'a line-break hyphen kept'),
    ('bv', 'by', Y, ''), ('flood control. Big Pine', 'flood control, Big Pine', Y, 'period for comma'), ('imless', 'unless', Y, ''),
    ('fimds', 'funds', Y, ''), ('e£U3t', 'east', Y, ''), ('chcumel', 'channel', Y, ''), ('Newbmyport', 'Newburyport', Y, ''),
    ('autiborized', 'authorized', Y, ''), ('Conmiencing', 'Commencing', Y, ''), ('seconcUi', 'seconds', Y, ''),
    ('MiCfflGAN', 'MICHIGAN', Y, ''), ('comer', 'corner', Y, ''), ('turning basin. Federal', 'turning basin, Federal', Y, 'read from the page'),
    ('Michig£ui', 'Michigan', Y, ''), ("purposes'*", 'purposes"', Y, ''),
    ('project. South Haven', 'project, South Haven', Y, 'read from the page'), ('tnence', 'thence', Y, ''),
    ('^ v e r and Harbor', 'River and Harbor', Y, 'letter-spaced'), ('Intermodel', 'Intermodal', Y, ''), ('niunbered', 'numbered', Y, ''),
    ('dociunent', 'document', Y, ''), ('otiier', 'other', Y, ''), ('Hsurdm', 'Hardin', Y, 'read from the page'),
    ('docimient', 'document', Y, ''), ('designated sis the', 'designated as the', Y, ''), ('BuENA', 'BUENA', Y, ''),
    ('shcdl', 'shall', Y, ''), ('Ftoject', 'Project', Y, ''), ('GALUPOUS', 'GALLIPOLIS', Y, ''), ('(aXl8XB)', '(a)(18)(B)', Y, ''),
    ('(aX24)', '(a)(24)', Y, ''),
    # ---- title II
    ('TTie', 'The', Y, ''), ('(aX12)', '(a)(12)', Y, ''), ('flood control. Feather Creek', 'flood control, Feather Creek', Y, 'period for comma'),
    ('flood control. Perry Creek', 'flood control, Perry Creek', Y, 'period for comma'),
    ('Grenevieve', 'Genevieve', Y, 'the heading reads GENEVIEVE'), ('Secretai^', 'Secretary', Y, ''), ('wmch', 'which', Y, ''),
    ('pav', 'pay', Y, ''), ('aquatic cuid', 'aquatic and', Y, ''), ('maintensince', 'maintenance', Y, ''), ('Such simis', 'Such sums', Y, ''),
    ('c a n y out', 'carry out', Y, 'letter-spaced'), ('doUar', 'dollar', Y, ''), ('a4justed', 'adjusted', Y, ''),
    ('studies.and', 'studies and', Y, ''), ('non-F^eral', 'non-Federal', Y, ''), ('wiU', 'will', Y, ''), ('W£U3', 'was', Y, ''),
    ('AUTHORITY To CARRY', 'AUTHORITY TO CARRY', Y, 'small capitals read as small letters'), ('reauired', 'required', Y, ''),
    ('oraer', 'order', Y, ''), ('concQtions', 'conditions', Y, ''), ('construction of uie project', 'construction of the project', Y, ''),
    ('environmenttdly', 'environmentally', Y, ''), ('regultirly', 'regularly', Y, ''), ('poUtical', 'political', Y, ''),
    ('pa3nnents', 'payments', Y, ''), ('iinder', 'under', Y, ''), ('maximimi', 'maximum', Y, ''), ('£ifter', 'after', Y, ''),
    ('•^(3) m-KiND', '"(3) IN-KIND', Y, 'read from the page'), ('Up to Vi of', 'Up to 1/2 of', Y, 'read from the page: ½'),
    ('the plan. ; and', 'the plan."; and', Y, 'read from the page: a closing quotation mark'), ('tnis', 'this', Y, ''),
    ('MussERS', 'MUSSERS', Y, ''), ('Ucense', 'license', Y, ''), ('responsibiUties', 'responsibilities', Y, ''),
    ('autihorized', 'authorized', Y, ''), ('P R O M O T I O N OF S A F E T Y P R O G R A M', 'PROMOTION OF SAFETY PROGRAM', Y, 'letter-spaced'),
    ('necessaiy', 'necessary', Y, ''), ('U S E O F PRIVATE', 'USE OF PRIVATE', Y, 'letter-spaced'), ('P R O D U C T S', 'PRODUCTS', Y, 'letter-spaced'),
    ('lOa-lOc', '10a-10c', Y, ''), ('APPUCABIUTY', 'APPLICABILITY', Y, ''), ('DEFmmONS', 'DEFINITIONS', Y, ''), ('suppUes', 'supplies', Y, ''),
    ('R U R A L P R O J E C T', 'RURAL PROJECT', Y, 'letter-spaced'), ('afl»r', 'after', Y, ''), ('Conunittee', 'Committee', Y, ''),
    ('£ind', 'and', Y, ''), ('Secrettuy', 'Secretary', Y, ''), ('shidl', 'shall', Y, ''), ('except t^at', 'except that', Y, ''),
    ('Caliiomia', 'California', Y, ''), ('\\^ter Resources', 'Water Resources', Y, ''), ('FACIU-TIES', 'FACILITIES', Y, ''),
    ('S A N T A ROSA WATER R E U S E P R O J E C T S', 'SANTA ROSA WATER REUSE PROJECTS', Y, 'letter-spaced'),
    ('CaUfomia', 'California', Y, ''), ('Assistence', 'Assistance', Y, ''), ('nonpoteble', 'nonpotable', Y, ''),
    ('groimdwater', 'groundwater', Y, ''), ('reqmrements', 'requirements', Y, ''), ('f^m', 'from', Y, ''), ('quaUty', 'quality', Y, ''),
    ('Anacostia Itiver', 'Anacostia River', Y, ''), ('UtiUty', 'Utility', Y, ''), ('government imits', 'government units', Y, ''),
    ('Qusmry', 'Quarry', Y, ''), ('pleuit', 'plant', Y, ''), ('Ljrnchburg', 'Lynchburg', Y, ''), ('non-Feder£j', 'non-Federal', Y, ''),
    ('control plana', 'control plans', Y, 'read from the page'), ('fi*om', 'from', Y, ''), ('SYS-TEM', 'SYSTEM', Y, 'a line-break hyphen kept'),
    ('Biiffalo', 'Buffalo', Y, ''), ('Totsd', 'Total', Y, ''), ('piuposes', 'purposes', Y, ''),
    # ---- title III
    ('boimded', 'bounded', Y, ''), ('Atehafalaya', 'Atchafalaya', Y, ''), ('Environmentid', 'Environmental', Y, ''),
    ('Grovemor', 'Governor', Y, ''), ('AUTHORIZATION OP APPROPRIATIONS', 'AUTHORIZATION OF APPROPRIATIONS', Y, ''),
    ('GeK)rge', 'George', Y, ''), ('groimd', 'ground', Y, ''), ('DESCMPTION', 'DESCRIPTION', Y, ''), ('fi:om', 'from', Y, ''),
    ('frt)m', 'from', Y, ''), ('Penobscot l^ver', 'Penobscot River', Y, ''), ('design ofprojects', 'design of projects', Y, ''),
    ('efrective', 'effective', Y, ''), ('shaU', 'shall', Y, ''), ('idsPORT', 'REPORT', Y, 'read from the page'),
    ('iSeptember', 'September', Y, ''), ('memorandimi oiunderstanding', 'memorandum of understanding', Y, ''),
    ('TchoutacaboufTa', 'Tchoutacabouffa', Y, ''), ('irhe', 'The', Y, ''), ('schedide', 'schedule', Y, ''), ('(2XB)', '(2)(B)', Y, ''),
    ('(2XC)', '(2)(C)', Y, ''), ('CHANNE:L', 'CHANNEL', Y, ''), ('SJecretsury', 'Secretary', Y, ''), ('Rejrnolds', 'Reynolds', Y, ''),
    ('ITie', 'The', Y, ''), ('docimients', 'documents', Y, ''), ('E A S T RIVER', 'EAST RIVER', Y, 'letter-spaced'),
    ('N E W', 'NEW', Y, 'letter-spaced'), ('Such siuns', 'Such sums', Y, ''), ('expenaed', 'expended', Y, ''),
    ('c a r ^ out', 'carry out', Y, 'letter-spaced'), ('Chamg lain', 'Champlain', Y, ''), ('modifymg', 'modifying', Y, ''),
    ('shsdl', 'shall', Y, ''), ('imdertake', 'undertake', Y, ''), ('arawdown', 'drawdown', Y, ''), ('Aj*my', 'Army', Y, ''),
    ('Secret€iry', 'Secretary', Y, ''), ('estab-Ush', 'establish', Y, ''),
    ('waterrelated', 'water-related', L, 'the print breaks it at a line end after "water-"'),
    ('S A R C D COUNCIL', 'SARCD COUNCIL', Y, 'letter-spaced'), ('ofiicials', 'officials', Y, ''), ('EstabUshment', 'Establishment', Y, ''),
    ('eCTective', 'effective', Y, ''), ('non-Feder£d', 'non-Federal', Y, ''), ('Federad', 'Federal', Y, ''),
    ('Such avana', 'Such sums', Y, 'read from the page'), ('fiscsu', 'fiscal', Y, ''), ('CounciF', 'Council"', Y, ''),
    ('Camhria', 'Cambria', Y, ''), ('^The Secretary shall, with', 'The Secretary shall, with', Y, 'a stray mark after the heading'),
    ('purpoises', 'purposes', Y, ''), ('ILLINOIS ANA MICHIGAN', 'ILLINOIS AND MICHIGAN', Y, ''), ('Land IVust', 'Land Trust', Y, ''),
    ('KENTUCKV', 'KENTUCKY', Y, ''), ('imi)lemented', 'implemented', Y, ''), ('subsection (a) snail', 'subsection (a) shall', Y, ''),
    ("infi'astructiu^", 'infrastructure', Y, ''), ('ai>propriated', 'appropriated', Y, ''), ('chsuige', 'change', Y, ''),
    ('or anv facilities', 'or any facilities', Y, ''), ('Secretanr', 'Secretary', Y, ''), ('fiood', 'flood', Y, ''),
    ('peircel', 'parcel', Y, ''), ('T47N, RIE', 'T47N, R1E', Y, 'read from the page'), ('Chmpewa', 'Chippewa', Y, ''),
    ('Secreta^ is', 'Secretary is', Y, ''), ('Mitigation Euid', 'Mitigation and', Y, ''), ('Watersned', 'Watershed', Y, ''),
    ('Penhom', 'Penhorn', Y, 'read from the page'), ('pcircent', 'percent', Y, ''), ('c£irry', 'carry', Y, ''),
    ('CoiromONS', 'CONDITIONS', Y, ''), ('operatea', 'operated', Y, ''), ('stud^^', 'study', Y, ''),
    ('models, ana to', 'models, and to', Y, ''),
    ('SxUDY.^The', 'STUDY.—The', Y, 'read from the page; the dash was misread, so the build missed this heading and will now read it'),
    ('identifyiing', 'identifying', Y, ''), ('location emd nature', 'location and nature', Y, ''), ('llie', 'The', Y, ''),
    ('aft«r', 'after', Y, ''), ('prmection', 'projection', Y, ''), ('into me trust mnd.', 'into the trust fund.', Y, ''),
    ('(aX3)', '(a)(3)', Y, ''), ('Federal*.', 'Federal".', Y, 'a closing quotation mark'), ('OLUO', 'OHIO', Y, ''),
    ('^s-inch', '5/8-inch', Y, 'read from the page: the print has ⅝'), ('idong', 'along', Y, ''), ('along tike arc', 'along the arc', Y, ''),
    ('northecusterly', 'northeasterly', Y, ''), ('right-of-way Une', 'right-of-way line', Y, ''), ('APPUCABILITY', 'APPLICABILITY', Y, ''),
    ('T O B E DECLARED', 'TO BE DECLARED', Y, 'letter-spaced'), ('VIR-GINIA', 'VIRGINIA', Y, 'a line-break hyphen kept'),
    ('CARO-LINA', 'CAROLINA', Y, 'a line-break hyphen kept'), ("estabh'.sh", 'establish', Y, ''),
    ('southern ^^^st Virginia', 'southern West Virginia', Y, ''), ('laciUties', 'facilities', Y, ''), ('avidlable', 'available', Y, ''),
    ('navigation. Port Everglades, Florida', 'navigation, Port Everglades, Florida', Y, 'period for comma'),
    ('flood control. Red Rock', 'flood control, Red Rock', Y, 'period for comma'),
    ('Ten-nessee', 'Tennessee', Y, 'a line-break hyphen kept'), ('studv', 'study', Y, ''), (')roject referred', 'project referred', Y, ''),
    ('being inimdated by E', 'being inundated by', Y, 'read from the page: the print has "inundated by high reservoir levels"'),
    ('lign reservoir', 'high reservoir', Y, 'read from the page: the scan split "high" into a line holding only "E" and "lign"; that made the rest of paragraph (1) a separate unnumbered piece, which now goes back into paragraph (1), so the act has one piece fewer'),
    ('(bXD', '(b)(1)', Y, ''), ('rightsof-way', 'rights-of-way', Y, ''), ('BEN-TON', 'BENTON', Y, 'a line-break hyphen kept'),
    ('ENHANCE-MENT', 'ENHANCEMENT', Y, 'a line-break hyphen kept'), ('a4jacent', 'adjacent', Y, ''), ('Resoiu-ces', 'Resources', Y, ''),
    ('lOl(n)', '101(n)', Y, ''), ('reqmres', 'requires', Y, ''), ('acqmred', 'acquired', Y, ''), ('membiers', 'members', Y, ''),
    ('agen<7', 'agency', Y, ''), ('Ih*otection', 'Protection', Y, ''), ('inserthig', 'inserting', Y, ''), ('Oi^tober', 'October', Y, ''),
    # ---- title IV
    ('si^iificantly', 'significantly', Y, ''), ('waterbome', 'waterborne', Y, ''), ('both mland', 'both inland', Y, ''),
    ('d r e ^ ^ g', 'dredging', Y, 'letter-spaced'), ("htu'bors", 'harbors', Y, ''), ('t3rpes', 'types', Y, ''), ('fiiture', 'future', Y, ''),
    ('of tMs Act', 'of this Act', Y, ''), ('PubUc', 'Public', Y, ''), ('tiiis', 'this', Y, ''), ('vdthin', 'within', Y, ''),
    # ---- title V
    ('fix)m', 'from', Y, ''), ('Uiose', 'those', Y, ''), ('(bX4)', '(b)(4)', Y, ''), ('condfucted', 'conducted', Y, ''),
    ('Research, smd Sanctuaries', 'Research, and Sanctuaries', Y, ''), ('Secretar^s', "Secretary's", Y, ''),
    ('Admimstrator', 'Administrator', Y, ''), ('sucn', 'such', Y, ''), ('da^s', 'days', Y, ''), ('vdth', 'with', Y, ''),
    ('decUnes', 'declines', Y, ''), ('himian', 'human', Y, ''), ('dimiping', 'dumping', Y, ''), ('paramoimt', 'paramount', Y, ''),
    ('£my', 'any', Y, ''), ('induding', 'including', Y, ''), ('conjimction', 'conjunction', Y, ''), ('unaccepteble', 'unacceptable', Y, ''),
    ('(aX4)', '(a)(4)', Y, ''), ('limitetions', 'limitations', Y, ''), ('iised', 'used', Y, ''), ('faciUtate', 'facilitate', Y, ''),
]
RULES = [(r'\b(\d{1,2}),((?:19|20)\d\d)\b', r'\1, \2', Y, 'a date printed without the space after its comma'),
         (r'\bI N (?=GENERAL(?!,--))', 'IN ', Y, 'letter-spaced')]

doc = json.load(open(sdir / 'WRDA 1992.structure.json', encoding='utf-8'))


def walk(u):
    yield u
    for c in u.get('children', []):
        yield from walk(c)


units = [u for s in doc['sections'] for u in walk(s)]


def cite(uid):
    parts = uid.split('.')[1:]
    return 'sec. ' + parts[0] + ''.join(f'({p})' if not re.fullmatch(r'i\d+', p) else f', item {int(p[1:])}' for p in parts[1:])


def find(pattern):
    hits = []
    for u in units:
        for fld in ('heading', 'own_text', 'trailing_text'):
            t = u.get(fld) or ''
            for m in pattern.finditer(t):
                hits.append((u['id'], fld, t, m.start(), m.end()))
    return hits


rows = []
for was, now, sure, note in FIX:
    pat = re.compile(('(?<![A-Za-z])' if was[0].isalpha() else '') + re.escape(was).replace('\\ ', '\\s+') + ('(?![A-Za-z])' if was[-1].isalpha() else ''))
    rows.append((was, now, sure, note, find(pat)))
for rx, repl, sure, note in RULES:
    hits = find(re.compile(rx))
    ex = hits[0][2][hits[0][3]:hits[0][4]] if hits else rx
    rows.append((ex, re.sub(rx, repl, ex), sure, note + ' (every such place)', hits))
rows.sort(key=lambda r: (min((units.index(next(u for u in units if u['id'] == h[0])) for h in r[4]), default=10 ** 6)))

missing = [r[0] for r in rows if not r[4]]
E = html.escape
tr, tsv = [], []
for n, (was, now, sure, note, hits) in enumerate(rows, 1):
    ctx = []
    for uid, fld, t, a, b in hits[:2]:
        ctx.append(f'<div class="c">…{E(t[max(0, a - 48):a])}<mark>{E(t[a:b])}</mark>{E(t[b:b + 48])}…</div>')
    where = cite(hits[0][0]) + (' heading' if hits and hits[0][1] == 'heading' else '') if hits else 'NOT FOUND'
    more = f'<div class="n">{len(hits)} places</div>' if len(hits) > 1 else ''
    tr.append(f'<tr class="{sure}" data-n="{n}"><td class="no">{n}</td><td>{E(where)}{more}</td><td class="w">{E(was)}</td>'
              f'<td class="f">{E(now)}</td><td>{"".join(ctx)}</td><td class="s">{ {"yes": "", "look": "worth a look", "page": "needs the page"}[sure] }'
              f'{("<div class=n>" + E(note) + "</div>") if note else ""}</td>'
              f'<td class="t"><label><input type="checkbox"> no</label><input type="text" placeholder="note"></td></tr>')
    for uid, fld, t, a, b in hits:
        tsv.append({'row': n, 'unit': uid, 'field': fld, 'as_scanned': was, 'planned_fix': now, 'sure': sure, 'note': note,
                    'context': (t[max(0, a - 48):a] + '[' + t[a:b] + ']' + t[b:b + 48]).replace('\n', ' ')})
n_places = sum(len(r[4]) for r in rows)
page = f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><title>WRDA 1992 misreads to review</title>
<style>
body {{ font: 14px/1.45 -apple-system, "Segoe UI", sans-serif; margin: 24px auto; max-width: 1280px; padding: 0 16px; color: #1c1c1c; }}
h1 {{ font-size: 20px; }} p {{ max-width: 60em; }}
table {{ border-collapse: collapse; width: 100%; }} th, td {{ border-bottom: 1px solid #ddd; padding: 5px 8px; vertical-align: top; text-align: left; }}
th {{ position: sticky; top: 0; background: #f3f2ee; }} .no {{ color: #777; text-align: right; }}
.w {{ font-family: ui-monospace, Menlo, monospace; color: #9b1c1c; white-space: nowrap; }} .f {{ font-family: ui-monospace, Menlo, monospace; color: #14622d; white-space: nowrap; }}
.c {{ font-family: Georgia, serif; }} mark {{ background: #ffe58a; }} .n {{ font-size: 12px; color: #777; }}
tr.look .s {{ color: #8a5a00; }} tr.page .s {{ color: #9b1c1c; }} tr.down td {{ background: #fdeceb; }}
.t {{ white-space: nowrap; }} .t input[type=text] {{ width: 150px; margin-left: 6px; }}
#out {{ width: 100%; height: 70px; font: 13px ui-monospace, Menlo, monospace; }} .bar {{ position: sticky; bottom: 0; background: #fff; padding: 10px 0; border-top: 2px solid #1c1c1c; }}
</style></head><body>
<h1>WRDA 1992: words the scan misread, and the planned fix</h1>
<p>{len(rows)} rows covering {n_places} places in the act. Red is what the scan gives; green is what I would put. A row with several places is fixed the same way in each.
Tick <b>no</b> on any row you do not want fixed as shown, and add a note if you like. Everything not ticked counts as a thumbs up.
When you are done, copy the line in the box at the bottom and paste it to me.</p>
<p><b>Worth a look</b> marks my best reading where the print could differ. Where the scan could not settle a word, I read the page image first: those rows say "read from the page".</p>
<table><thead><tr><th>#</th><th>Where</th><th>As scanned</th><th>Planned fix</th><th>Context</th><th>How sure</th><th>Your call</th></tr></thead>
<tbody>{"".join(tr)}</tbody></table>
<div class="bar"><textarea id="out" readonly></textarea></div>
<script>
const KEY = "wrda1992-misreads";
let saved = {{}}; try {{ saved = JSON.parse(localStorage.getItem(KEY) || "{{}}"); }} catch (e) {{}}
const rows = [...document.querySelectorAll("tbody tr")];
function tell() {{
  const no = [], notes = []; const state = {{}};
  rows.forEach(r => {{ const n = r.dataset.n, box = r.querySelector("input[type=checkbox]"), note = r.querySelector("input[type=text]").value.trim();
    r.classList.toggle("down", box.checked); if (box.checked) no.push(n); if (note) notes.push(n + ": " + note); if (box.checked || note) state[n] = [box.checked, note]; }});
  document.getElementById("out").value = "WRDA 1992 misreads. Thumbs down on rows: " + (no.join(", ") || "none") + ". Notes: " + (notes.join(" | ") || "none") + ". All other rows: thumbs up.";
  try {{ localStorage.setItem(KEY, JSON.stringify(state)); }} catch (e) {{}}
}}
rows.forEach(r => {{ const s = saved[r.dataset.n]; if (s) {{ r.querySelector("input[type=checkbox]").checked = s[0]; r.querySelector("input[type=text]").value = s[1]; }}
  r.addEventListener("input", tell); }});
tell();
</script></body></html>'''
odir.mkdir(parents=True, exist_ok=True)
(odir / 'WRDA 1992 misreads to review.html').write_text(page, encoding='utf-8')
with open(odir / 'WRDA 1992 misreads to review.tsv', 'w', encoding='utf-8', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=['row', 'unit', 'field', 'as_scanned', 'planned_fix', 'sure', 'note', 'context'], delimiter='\t')
    w.writeheader()
    w.writerows(tsv)
print(f'{len(rows)} rows, {n_places} places; by how sure: {dict(collections.Counter(r[2] for r in rows))}')
print('NOT FOUND in the text (my slip, to correct):', missing or 'none')
many = [(r[0], len(r[4])) for r in rows if len(r[4]) > 1]
print('rows with several places:', many)
# ---- things still to look at before the table is final
allt = [(u['id'], t) for u in units for t in (u.get('heading') or '', u.get('own_text') or '') if t]
print("'I N' places:", [(i[5:], t[m.start():m.end() + 22]) for i, t in allt for m in re.finditer(r'\bI N\b', t)])
print('other X-for-")(" places:', sorted({m.group() for i, t in allt for m in re.finditer(r'\(\w{1,3}X\w{1,3}\)', t)}))
print('period then a place name:', [(i[5:], t[max(0, m.start() - 22):m.end() + 26]) for i, t in allt
      for m in re.finditer(r'\b(?:control|navigation|protection|restoration|project|purposes|River|Harbor|Lake|Creek|Dam)\. (?!The |Such |Any |In |If |No |Not |Nothing |Upon |For |Before |Within |Each |This |Section |Subsection |Paragraph |Notwithstanding |After |Funds |There |Sec\. |Subject |Except |To |As |At |On |With |Non|Any|All |An |A |Of |Until |Unless |Prior |During |Beginning |Thence |Running )[A-Z][a-z]+', t)][:25])
