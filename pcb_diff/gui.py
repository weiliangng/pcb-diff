"""Small native file-picker interface; core comparisons run in a worker thread."""
from datetime import datetime
from pathlib import Path
import queue
import json
import sys
import threading
import tkinter as tk
from tkinter import filedialog,messagebox,ttk
import webbrowser

def main(self_test_dir=None):
    app = tk.Tk()
    if self_test_dir:
        app.withdraw()
    app.title('PCB Diff')
    app.minsize(680,540)
    panel = ttk.Frame(app,padding=20)
    panel.pack(fill='both',expand=True)
    panel.columnconfigure(1,weight=1)
    fields = {key:tk.StringVar() for key in ['old','new','output','map']}
    fields['output'].set(str(Path.cwd()/'comparisons'/datetime.now().strftime('%Y%m%d-%H%M%S')))
    def pick_file(key):
        path = filedialog.askopenfilename(title='Choose '+('older' if key=='old' else 'newer')+' Gerber input',filetypes=[('All files','*.*')])
        if path: fields[key].set(path)
    def pick_folder(key):
        path = filedialog.askdirectory(title='Choose '+key+' folder')
        if path:
            if key=='output': path = str(Path(path)/('pcb-diff-'+datetime.now().strftime('%Y%m%d-%H%M%S')))
            fields[key].set(path)
    ttk.Label(panel,text='Compare two Gerber exports',font=('TkDefaultFont',16)).grid(row=0,column=0,columnspan=4,sticky='w',pady=(0,16))
    ttk.Label(panel,text='Choose archives, folders, or two individual layer files.').grid(row=1,column=0,columnspan=4,sticky='w',pady=(0,14))
    for row,(key,label) in enumerate([('old','Older input'),('new','Newer input')],2):
        ttk.Label(panel,text=label).grid(row=row,column=0,sticky='w',padx=(0,12),pady=5)
        ttk.Entry(panel,textvariable=fields[key]).grid(row=row,column=1,sticky='ew',pady=5)
        ttk.Button(panel,text='File…',command=lambda k=key:pick_file(k)).grid(row=row,column=2,padx=5)
        ttk.Button(panel,text='Folder…',command=lambda k=key:pick_folder(k)).grid(row=row,column=3)
    ttk.Label(panel,text='Save results').grid(row=4,column=0,sticky='w',padx=(0,12),pady=5)
    ttk.Entry(panel,textvariable=fields['output']).grid(row=4,column=1,sticky='ew',pady=5)
    ttk.Button(panel,text='Choose…',command=lambda:pick_folder('output')).grid(row=4,column=2,columnspan=2,sticky='ew',padx=(5,0))
    controls = ttk.Frame(panel)
    controls.grid(row=5,column=0,columnspan=4,sticky='ew',pady=12)
    dpmm,tolerance,scope = tk.StringVar(value='50'),tk.StringVar(value='0.02'),tk.StringVar(value='copper')
    for i,(label,variable) in enumerate([('Pixels/mm',dpmm),('Edge tolerance (mm)',tolerance)]):
        ttk.Label(controls,text=label).grid(row=0,column=i*2,padx=(0,8),sticky='w')
        ttk.Entry(controls,textvariable=variable,width=8).grid(row=0,column=i*2+1,padx=(0,18))
    ttk.Label(controls,text='Layers').grid(row=0,column=4,padx=(0,8))
    ttk.Combobox(controls,textvariable=scope,values=['copper','all'],state='readonly',width=10).grid(row=0,column=5)
    def choose_map():
        path = filedialog.askopenfilename(title='Choose explicit layer map',filetypes=[('JSON','*.json')])
        if path: fields['map'].set(path)
    ttk.Label(panel,text='Layer map (optional)').grid(row=6,column=0,sticky='w',padx=(0,12),pady=5)
    ttk.Entry(panel,textvariable=fields['map']).grid(row=6,column=1,sticky='ew')
    ttk.Button(panel,text='Choose…',command=choose_map).grid(row=6,column=2,columnspan=2,sticky='ew',padx=(5,0))
    ttk.Label(panel,text='Added copper is green; removed copper is red. Exact and edge-tolerant images are saved.').grid(row=7,column=0,columnspan=4,sticky='w',pady=12)
    log = tk.Text(panel,height=9,state='disabled',wrap='word')
    log.grid(row=8,column=0,columnspan=4,sticky='nsew')
    panel.rowconfigure(8,weight=1)
    status = tk.StringVar(value='Ready')
    ttk.Label(panel,textvariable=status).grid(row=9,column=0,columnspan=2,sticky='w',pady=12)
    events,result = queue.Queue(),{'folder':None}
    def append(text):
        log.configure(state='normal')
        log.insert('end',text+'\n')
        log.see('end')
        log.configure(state='disabled')
    def worker(old,new,output,config):
        try:
            from .core import compare
            compare(old,new,output,config,progress=lambda text:events.put(('progress',text)))
            events.put(('success',str(Path(output).resolve())))
        except Exception as error:
            events.put(('error',str(error)))
    def start():
        try:
            from .core import Options,validate
            config = Options(dpmm=float(dpmm.get()),tolerance_mm=float(tolerance.get()),scope=scope.get(),layer_map=fields['map'].get() or None)
            validate(config)
            old,new,output = [fields[k].get().strip() for k in ('old','new','output')]
            if not old or not new or not output: raise ValueError('Choose both inputs and an output location.')
        except ImportError as error:
            messagebox.showerror('Setup required',str(error)+'\nRun setup-windows.cmd or install requirements.txt.')
            return
        except (ValueError,OSError) as error:
            messagebox.showerror('Check settings',str(error))
            return
        run.configure(state='disabled')
        open_button.configure(state='disabled')
        status.set('Comparing…')
        result['folder']=None
        threading.Thread(target=worker,args=(old,new,output,config),daemon=True).start()
    run = ttk.Button(panel,text='Compare',command=start)
    run.grid(row=9,column=2,padx=5,pady=12)
    open_button = ttk.Button(panel,text='Open report',state='disabled',command=lambda:webbrowser.open((Path(result['folder'])/'report.html').as_uri()))
    open_button.grid(row=9,column=3,pady=12)
    def poll():
        while not events.empty():
            kind,value = events.get_nowait()
            append(value)
            if kind=='success':
                result['folder']=value
                status.set('Finished')
                run.configure(state='normal')
                open_button.configure(state='normal')
                if self_test_dir:
                    summary = json.loads((Path(value)/'results.json').read_text(encoding='utf-8'))
                    row = summary['layers'][0]
                    passed = row['exact_added_mm2'] > 0 and row['exact_removed_mm2'] == 0
                    (Path(self_test_dir)/'gui-self-test.json').write_text(json.dumps({'passed':passed,'report_enabled':True}),encoding='utf-8')
                    app.destroy()
                    if not passed:
                        raise RuntimeError('GUI self-test found unexpected subtraction results.')
                    return
            elif kind=='error':
                status.set('Comparison failed')
                run.configure(state='normal')
                if self_test_dir:
                    (Path(self_test_dir)/'gui-self-test.json').write_text(json.dumps({'passed':False,'error':value}),encoding='utf-8')
                    app.destroy()
                    return
                messagebox.showerror('Comparison failed',value)
        app.after(100,poll)
    if self_test_dir:
        fixture_root = Path(self_test_dir).resolve()
        fixture_root.mkdir(parents=True,exist_ok=True)
        code = '%FSLAX45Y45*%\n%MOMM*%\n%ADD10C,1*%\nD10*\nX200000Y300000D03*\n'
        (fixture_root/'old.gbr').write_text(code+'M02*',encoding='ascii')
        (fixture_root/'new.gbr').write_text(code+'X500000Y600000D03*\nM02*',encoding='ascii')
        fields['old'].set(str(fixture_root/'old.gbr'))
        fields['new'].set(str(fixture_root/'new.gbr'))
        fields['output'].set(str(fixture_root/'comparison'))
        app.after(50,run.invoke)
        def timeout():
            (fixture_root/'gui-self-test.json').write_text(json.dumps({'passed':False,'error':'GUI self-test timeout'}),encoding='utf-8')
            app.destroy()
        app.after(90000,timeout)
    poll()
    app.mainloop()

if __name__=='__main__': main()
