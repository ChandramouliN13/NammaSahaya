from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from pathlib import Path
from difflib import SequenceMatcher
import sqlite3, re, urllib.parse, hashlib, secrets, math
from .database import conn, init_db, DB_PATH

BASE=Path(__file__).resolve().parent.parent
app=FastAPI(title='NammaSahaya',version='4.0.0')
app.mount('/static',StaticFiles(directory=BASE/'static'),name='static')

@app.on_event('startup')
def startup(): init_db()
@app.get('/',response_class=HTMLResponse)
def home(): return (BASE/'static/index.html').read_text(encoding='utf-8')

def clean(s): return re.sub(r'\s+',' ',(s or '').lower()).strip()
def all_services():
    c=conn(); rows=c.execute('SELECT * FROM services ORDER BY category,name_en').fetchall(); c.close(); return [dict(r) for r in rows]
def service(sid):
    c=conn(); r=c.execute('SELECT * FROM services WHERE id=?',(sid,)).fetchone(); c.close()
    if not r: raise HTTPException(404,'Service not found')
    return dict(r)
def user(uid):
    c=conn(); r=c.execute('SELECT id,name,email,role,created_at FROM users WHERE id=?',(uid,)).fetchone(); c.close(); return dict(r) if r else None

ALIASES={
'pension':['pension','old age','senior','widow','ಪಿಂಚಣಿ','ವೃದ್ಧ','ಹಿರಿಯ'],'scholarship':['scholarship','student money','education money','fee','student','ವಿದ್ಯಾರ್ಥಿವೇತನ','ವಿದ್ಯಾರ್ಥಿ','ಶುಲ್ಕ'],'job':['job','work','employment','career','vacancy','recruitment','ಕೆಲಸ','ಉದ್ಯೋಗ','ನೇಮಕಾತಿ'],'road':['road','pothole','street','ರಸ್ತೆ','ಗುಂಡಿ'],'garbage':['garbage','waste','trash','kasa','ಕಸ','ತ್ಯಾಜ್ಯ'],'water':['water','tap','drinking water','supply','ನೀರು'],'drain':['drain','drainage','sewage','overflow','ಚರಂಡಿ','ಒಳಚರಂಡಿ'],'light':['streetlight','street light','lamp','light','ದೀಪ'],'khata':['khata','e khata','property','land','house','ಆಸ್ತಿ','ಖಾತಾ','ಮನೆ','ಜಮೀನು'],'certificate':['certificate','proof','ಪ್ರಮಾಣ ಪತ್ರ'],'birth':['birth','born','baby','ಜನನ','ಮಗು'],'death':['death','ಮರಣ'],'income':['income','salary','earnings','ಆದಾಯ','ಸಂಬಳ'],'caste':['caste','category','sc','st','obc','ಜಾತಿ'],'farmer':['farmer','farm','crop','agriculture','ರೈತ','ಕೃಷಿ','ಬೆಳೆ'],'ration':['ration','food','rice','card','ಪಡಿತರ','ಅಕ್ಕಿ','ಆಹಾರ'],'vehicle':['vehicle','car','bike','rto','registration','ವಾಹನ','ಕಾರು','ಬೈಕ್'],'licence':['licence','license','driving','dl','ಚಾಲನಾ','ಪರವಾನಗಿ'],'emergency':['emergency','ambulance','police','fire','urgent','ತುರ್ತು','ಆಂಬ್ಯುಲೆನ್ಸ್','ಪೊಲೀಸ್','ಅಗ್ನಿ'],'complaint':['complaint','complain','grievance','problem','issue','ದೂರು','ಸಮಸ್ಯೆ'],'seva':['seva sindhu','government service','online service','ಸೇವಾ ಸಿಂಧು','ಸರ್ಕಾರಿ ಸೇವೆ'],'sakala':['sakala','deadline','time bound','ಸಕಾಲ','ಕಾಲಮಿತಿ'],'tax':['tax','property tax','gst','income tax','ತೆರಿಗೆ'],'passport':['passport','ಪಾಸ್‌ಪೋರ್ಟ್'],'consumer':['consumer','shop complaint','fraud','ಗ್ರಾಹಕ','ದೂರು'],'skill':['skill','training','course','ಕೌಶಲ್ಯ','ತರಬೇತಿ'],'rti':['rti','right to information','ಮಾಹಿತಿ ಹಕ್ಕು'],'police':['police','fir','complaint police','ಪೊಲೀಸ್','ಎಫ್‌ಐಆರ್']}

def fuzzy(a,b): return SequenceMatcher(None,a,b).ratio() if a and b else 0

def score_service(q,s):
    q=clean(q); text=clean(' '.join(str(s.get(k,'')) for k in ['name_en','name_kn','description_en','description_kn','keywords','category','department']))
    score=0
    if q in text: score+=45
    qwords=[x for x in re.findall(r'[a-zA-Z0-9\u0C80-\u0CFF]+',q) if len(x)>1]
    candidates=re.findall(r'[a-zA-Z0-9\u0C80-\u0CFF]+',text)
    for w in qwords:
        if w in text: score+=10
        elif candidates and max(fuzzy(w,c) for c in candidates)>=.78: score+=6
    for intent,words in ALIASES.items():
        if any(clean(w) in q for w in words):
            if any(clean(w) in text for w in words): score+=25
            if intent=='complaint' and 'grievance' in clean(s['category']): score+=18
            if intent=='certificate' and 'certificate' in clean(s['category']): score+=12
            if intent=='job' and ('employment' in clean(s['category']) or 'skills' in clean(s['category'])): score+=12
    score += int(fuzzy(q,clean(s['name_en']))*14)
    return score

class SearchIn(BaseModel): query:str; language:str='en'; user_id:int|None=None; category:str|None=None; department:str|None=None
@app.post('/api/search')
def search(b:SearchIn):
    q=b.query.strip(); services=all_services()
    if b.category: services=[s for s in services if clean(s['category'])==clean(b.category)]
    if b.department: services=[s for s in services if clean(s.get('department'))==clean(b.department)]
    if b.user_id and q: log_activity(b.user_id,'search',q); save_search(b.user_id,q)
    if not q: return {'query':'','mode':'popular','suggestions':suggestions(''),'results':services[:12]}
    ranked=sorted([(score_service(q,s),s) for s in services],key=lambda x:x[0],reverse=True)
    strong=[(sc,s) for sc,s in ranked if sc>=14][:10]
    did=did_you_mean(q,services)
    if strong: return {'query':q,'mode':'matched','did_you_mean':did,'suggestions':suggestions(q),'results':[dict(s,match_score=sc) for sc,s in strong]}
    official='https://www.google.com/search?q='+urllib.parse.quote('site:karnataka.gov.in '+q)
    universal={'id':0,'name_en':f'Official service search: {q}','name_kn':f'ಅಧಿಕೃತ ಸೇವೆ ಹುಡುಕಾಟ: {q}','category':'Universal Government Search','department':'Government of Karnataka','description_en':'No exact catalog match. Search Karnataka Government domains for the current official service.','description_kn':'ನಿಖರ ಹೊಂದಾಣಿಕೆ ಸಿಗಲಿಲ್ಲ. ಕರ್ನಾಟಕ ಸರ್ಕಾರದ ಅಧಿಕೃತ ಡೊಮೇನ್‌ಗಳಲ್ಲಿ ಪ್ರಸ್ತುತ ಸೇವೆಯನ್ನು ಹುಡುಕಿ.','keywords':q,'application_url':official,'status_url':official,'official_url':official,'documents_en':'Check the official department page for the exact current document list.','steps_en':'Open the official result; choose the government domain; verify service name and department; apply only on the official portal.','eligibility_en':'Depends on the specific service.','fees_en':'Check the official portal.','processing_time_en':'Depends on the department.','helpline':'See the selected official department portal.','verified_on':'2026-09-07','universal':True,'match_score':1}
    return {'query':q,'mode':'universal_fallback','did_you_mean':did,'suggestions':suggestions(q),'results':[universal]+[dict(s,match_score=sc) for sc,s in ranked[:8]]}

def suggestions(q):
    if not q: return ['scholarship','pension','property tax','birth certificate','caste certificate','driving licence','farmer services','grievance']
    terms=['scholarship','pension','property tax','eKhata','income certificate','caste certificate','birth certificate','death certificate','ration card','farmer services','driving licence','vehicle registration','employment','skill training','RTI','police complaint','water complaint','garbage complaint']
    return sorted(terms,key=lambda x:fuzzy(clean(q),clean(x)),reverse=True)[:5]
def did_you_mean(q,services):
    if not q:return None
    names=[s['name_en'] for s in services]
    best=max(names,key=lambda n:fuzzy(clean(q),clean(n))) if names else None
    return best if best and fuzzy(clean(q),clean(best))>=.48 and clean(q)!=clean(best) else None

@app.get('/api/services')
def services(category:str|None=None,department:str|None=None,location:str|None=None):
    c=conn(); rows=c.execute('SELECT * FROM services ORDER BY category,name_en').fetchall(); c.close(); out=[dict(r) for r in rows]
    if category: out=[x for x in out if clean(x['category'])==clean(category)]
    if department: out=[x for x in out if clean(x.get('department'))==clean(department)]
    if location: out=[x for x in out if location.lower() in clean(x.get('location','')) or location.lower() in clean(x.get('description_en',''))]
    return out
@app.get('/api/services/{sid}')
def get_service(sid:int): return service(sid)
@app.get('/api/categories')
def categories(): return sorted({s['category'] for s in all_services()})
@app.get('/api/departments')
def departments(): return sorted({s['department'] for s in all_services() if s.get('department')})
@app.get('/api/health')
def health(): return {'status':'ok','database':'connected','service_count':len(all_services()),'version':'4.0.0'}

class EligibilityIn(BaseModel): age:int|None=None; resident:bool=True; student:bool=False; farmer:bool=False; senior:bool=False; income:float|None=None
@app.post('/api/eligibility/{sid}')
def eligibility(sid:int,b:EligibilityIn):
    s=service(sid); t=clean(s['name_en']+' '+s['keywords']); score=50; reasons=[]
    if b.resident: score+=10; reasons.append('Karnataka residence selected.')
    if b.student and any(x in t for x in ['student','scholarship','education']): score+=22; reasons.append('Student profile is relevant.')
    if b.farmer and any(x in t for x in ['farmer','agriculture','crop']): score+=22; reasons.append('Farmer profile is relevant.')
    if b.senior and any(x in t for x in ['senior','pension','old age']): score+=22; reasons.append('Senior-citizen profile is relevant.')
    if b.age is not None and b.age>=60 and any(x in t for x in ['senior','pension','old age']): score+=10; reasons.append('Age may be relevant to this service.')
    return {'result':'Likely relevant' if score>=75 else 'Possibly relevant','score':min(score,95),'reasons':reasons or ['Check the current official eligibility rules.'],'disclaimer':'Guidance only; the government department makes the final eligibility decision.'}

class ScamIn(BaseModel): text:str
@app.post('/api/scam-check')
def scam(b:ScamIn):
    t=clean(b.text); flags=[]; checks=[(['otp','one time password'],'Requests an OTP/verification code.'),(['upi','send money','pay rs','payment'],'Requests money or UPI payment.'),(['bit.ly','tinyurl','unknown link'],'Pushes a suspicious/shortened link.'),(['guaranteed government job','guaranteed scheme'],'Makes a guaranteed-benefit/job claim.'),(['urgent','immediately','today only'],'Uses pressure or urgency.'),(['password','pin','cvv'],'Requests sensitive credentials.')]
    for keys,msg in checks:
        if any(k in t for k in keys): flags.append(msg)
    risk=min(95,15+len(flags)*16); return {'risk_score':risk,'level':'High risk' if risk>=65 else ('Review carefully' if risk>=40 else 'No obvious red flags detected'),'red_flags':flags,'advice':'Never share OTP, PIN, CVV or passwords. Verify claims through official government websites.'}

class AuthRequest(BaseModel): name:str=''; email:str; password:str
class HistoryRequest(BaseModel): user_id:int; query:str
class ActivityRequest(BaseModel): user_id:int; action:str; details:str=''
class ApplicationRequest(BaseModel): user_id:int; service_id:int; reference:str
class SaveServiceRequest(BaseModel): user_id:int; service_id:int
class FeedbackRequest(BaseModel): user_id:int|None=None; service_id:int|None=None; rating:int; comment:str=''

def hash_password(password,salt): return hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),120000).hex()
def log_activity(uid,action,details=''):
    if not uid:return
    c=conn(); c.execute('INSERT INTO activity_history(user_id,action,details) VALUES(?,?,?)',(uid,action,details)); c.commit(); c.close()
def save_search(uid,q):
    if not uid:return
    c=conn(); c.execute('INSERT INTO search_history(user_id,query) VALUES(?,?)',(uid,q)); c.commit(); c.close()

@app.post('/api/auth/register')
def register(r:AuthRequest):
    email=r.email.strip().lower(); name=r.name.strip() or email.split('@')[0]
    if len(r.password)<6: raise HTTPException(400,'Password must be at least 6 characters')
    salt=secrets.token_hex(16); h=hash_password(r.password,salt); c=conn()
    try:
        cur=c.execute('INSERT INTO users(name,email,password_hash,password_salt,role) VALUES(?,?,?,?,?)',(name,email,h,salt,'user')); uid=cur.lastrowid; c.commit()
    except sqlite3.IntegrityError: c.close(); raise HTTPException(409,'Email already registered')
    c.close(); log_activity(uid,'account_created','Account created'); return {'user_id':uid,'id':uid,'name':name,'email':email,'role':'user'}
@app.post('/api/auth/login')
def login(r:AuthRequest):
    email=r.email.strip().lower(); c=conn(); u=c.execute('SELECT * FROM users WHERE email=?',(email,)).fetchone(); c.close()
    if not u or hash_password(r.password,u['password_salt'])!=u['password_hash']: raise HTTPException(401,'Invalid email or password')
    log_activity(u['id'],'login','User logged in'); return {'user_id':u['id'],'id':u['id'],'name':u['name'],'email':u['email'],'role':u['role']}
@app.post('/api/history/search')
def history_search(r:HistoryRequest):
    if r.query.strip(): save_search(r.user_id,r.query.strip()); log_activity(r.user_id,'search',r.query.strip())
    return {'ok':True}
@app.post('/api/activity')
def activity(r:ActivityRequest): log_activity(r.user_id,r.action,r.details); return {'ok':True}
@app.get('/api/history/{uid}')
def history(uid:int):
    c=conn(); searches=c.execute('SELECT id,query,created_at FROM search_history WHERE user_id=? ORDER BY id DESC LIMIT 200',(uid,)).fetchall(); acts=c.execute('SELECT id,action,details,created_at FROM activity_history WHERE user_id=? ORDER BY id DESC LIMIT 200',(uid,)).fetchall(); c.close(); return {'searches':[dict(x) for x in searches],'activity':[dict(x) for x in acts]}
@app.delete('/api/history/{uid}')
def clear_history(uid:int):
    c=conn(); c.execute('DELETE FROM search_history WHERE user_id=?',(uid,)); c.execute('DELETE FROM activity_history WHERE user_id=?',(uid,)); c.commit(); c.close(); return {'ok':True}

@app.post('/api/saved-services')
def save_service(r:SaveServiceRequest):
    service(r.service_id); c=conn(); c.execute('INSERT OR IGNORE INTO saved_services(user_id,service_id) VALUES(?,?)',(r.user_id,r.service_id)); c.commit(); c.close(); log_activity(r.user_id,'service_saved',f'service_id={r.service_id}'); return {'ok':True}
@app.delete('/api/saved-services/{uid}/{sid}')
def unsave_service(uid:int,sid:int):
    c=conn(); c.execute('DELETE FROM saved_services WHERE user_id=? AND service_id=?',(uid,sid)); c.commit(); c.close(); log_activity(uid,'service_unsaved',f'service_id={sid}'); return {'ok':True}

@app.get('/api/dashboard/{uid}')
def dashboard(uid:int):
    c=conn(); u=c.execute('SELECT id,name,email,role,created_at FROM users WHERE id=?',(uid,)).fetchone()
    if not u: c.close(); raise HTTPException(404,'User not found')
    searches=c.execute('SELECT id,query,created_at FROM search_history WHERE user_id=? ORDER BY id DESC LIMIT 12',(uid,)).fetchall()
    saved=c.execute('SELECT s.* FROM services s JOIN saved_services ss ON ss.service_id=s.id WHERE ss.user_id=? ORDER BY ss.id DESC',(uid,)).fetchall()
    apps=c.execute('SELECT a.id,a.reference,a.created_at,s.name_en,s.name_kn,s.application_url,s.status_url FROM applications a JOIN services s ON s.id=a.service_id WHERE a.user_id=? ORDER BY a.id DESC LIMIT 20',(uid,)).fetchall()
    viewed=c.execute("SELECT ah.details,ah.created_at,s.* FROM activity_history ah LEFT JOIN services s ON ah.details='service_id='||s.id WHERE ah.user_id=? AND ah.action='viewed_service' ORDER BY ah.id DESC LIMIT 10",(uid,)).fetchall()
    acts=c.execute('SELECT action,details,created_at FROM activity_history WHERE user_id=? ORDER BY id DESC LIMIT 15',(uid,)).fetchall()
    counts={'searches':c.execute('SELECT COUNT(*) n FROM search_history WHERE user_id=?',(uid,)).fetchone()['n'],'saved':c.execute('SELECT COUNT(*) n FROM saved_services WHERE user_id=?',(uid,)).fetchone()['n'],'applications':c.execute('SELECT COUNT(*) n FROM applications WHERE user_id=?',(uid,)).fetchone()['n'],'actions':c.execute('SELECT COUNT(*) n FROM activity_history WHERE user_id=?',(uid,)).fetchone()['n']}
    c.close(); return {'user':dict(u),'counts':counts,'searches':[dict(x) for x in searches],'saved':[dict(x) for x in saved],'applications':[dict(x) for x in apps],'viewed':[dict(x) for x in viewed if x['id'] is not None],'activity':[dict(x) for x in acts]}

@app.post('/api/applications')
def application(r:ApplicationRequest):
    service(r.service_id); c=conn(); cur=c.execute('INSERT INTO applications(user_id,service_id,reference) VALUES(?,?,?)',(r.user_id,r.service_id,r.reference)); c.commit(); aid=cur.lastrowid; c.close(); log_activity(r.user_id,'application_reference_saved',f'service_id={r.service_id}; reference={r.reference}'); return {'id':aid,'ok':True}

@app.post('/api/feedback')
def feedback(r:FeedbackRequest):
    if not 1<=r.rating<=5: raise HTTPException(400,'Rating must be 1-5')
    c=conn(); c.execute('INSERT INTO feedback(user_id,service_id,rating,comment) VALUES(?,?,?,?)',(r.user_id,r.service_id,r.rating,r.comment[:1000])); c.commit(); c.close();
    if r.user_id: log_activity(r.user_id,'feedback_submitted',f'service_id={r.service_id}; rating={r.rating}')
    return {'ok':True}

@app.get('/api/admin/summary')
def admin_summary(uid:int):
    u=user(uid)
    if not u or u.get('role')!='admin': raise HTTPException(403,'Admin access required')
    c=conn()
    total_users=c.execute('SELECT COUNT(*) n FROM users').fetchone()['n']; searches=c.execute('SELECT COUNT(*) n FROM search_history').fetchone()['n']; actions=c.execute('SELECT COUNT(*) n FROM activity_history').fetchone()['n']; feedbacks=c.execute('SELECT COUNT(*) n FROM feedback').fetchone()['n']
    top_searches=c.execute('SELECT query,COUNT(*) n FROM search_history GROUP BY query ORDER BY n DESC LIMIT 10').fetchall()
    top_views=c.execute("SELECT substr(details,11) service_id,COUNT(*) n FROM activity_history WHERE action='viewed_service' GROUP BY details ORDER BY n DESC LIMIT 10").fetchall()
    portal_clicks=c.execute("SELECT action,COUNT(*) n FROM activity_history WHERE action IN ('apply_link_clicked','status_link_clicked') GROUP BY action ORDER BY n DESC").fetchall()
    categories=c.execute('SELECT category,COUNT(*) n FROM services GROUP BY category ORDER BY n DESC').fetchall()
    daily=c.execute("SELECT substr(created_at,1,10) day,COUNT(*) n FROM activity_history GROUP BY day ORDER BY day DESC LIMIT 14").fetchall()
    usage=c.execute("SELECT s.name_en,s.category,COUNT(ah.id) n FROM services s LEFT JOIN activity_history ah ON ah.details='service_id='||s.id GROUP BY s.id ORDER BY n DESC LIMIT 15").fetchall()
    c.close(); return {'totals':{'users':total_users,'searches':searches,'actions':actions,'feedback':feedbacks},'top_searches':[dict(x) for x in top_searches],'top_views':[dict(x) for x in top_views],'portal_clicks':[dict(x) for x in portal_clicks],'categories':[dict(x) for x in categories],'daily_activity':[dict(x) for x in daily],'service_usage':[dict(x) for x in usage]}

@app.get('/api/admin/users')
def admin_users(uid:int):
    u=user(uid)
    if not u or u.get('role')!='admin': raise HTTPException(403,'Admin access required')
    c=conn(); rows=c.execute('SELECT id,name,email,role,created_at FROM users ORDER BY id DESC').fetchall(); c.close(); return [dict(x) for x in rows]

@app.get('/api/grievances')
def grievances():
    return [{'type':'Road / pothole','keywords':['road','pothole','ರಸ್ತೆ','ಗುಂಡಿ'],'guidance':'Take a photo, record the exact location/landmark, and submit through the official civic grievance route.'},{'type':'Garbage / sanitation','keywords':['garbage','waste','ಕಸ'],'guidance':'Record location, issue duration and a photo if useful, then use the official civic grievance route.'},{'type':'Water','keywords':['water','ನೀರು'],'guidance':'Record the affected address/locality, connection details if relevant and duration.'},{'type':'Drainage','keywords':['drain','drainage','ಚರಂಡಿ'],'guidance':'Photograph the overflow/blockage and record the exact location.'},{'type':'Streetlight','keywords':['light','streetlight','ದೀಪ'],'guidance':'Record the pole/location and describe whether the light is broken or unsafe.'}]
