#!/usr/bin/python3
"""Opt-in isolated GTK/IBus composition test; never uses the active desktop/bus.
Uses temporary XDG config/cache/runtime directories and a private IBus socket.
"""
import os, sys, subprocess, time, tempfile, selectors
from pathlib import Path

def worker():
    import gi
    gi.require_version('Gtk','3.0'); gi.require_version('IBus','1.0')
    from gi.repository import Gtk, Gdk, GLib, Gio, IBus
    import json
    daemon=subprocess.Popen(['ibus-daemon','--replace','--xim','--panel','disable','--emoji-extension','disable','--address',os.environ['IBUS_ADDRESS']],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        IBus.init()
        bus=IBus.Bus.new()
        deadline=time.monotonic()+8
        while not bus.is_connected():
            if time.monotonic()>deadline: raise RuntimeError('isolated IBus did not start')
            while GLib.MainContext.default().pending(): GLib.MainContext.default().iteration(False)
            time.sleep(.1)
            bus=IBus.Bus.new()
        settings=Gio.Settings.new('org.freedesktop.ibus.engine.hangul')
        settings.set_string('switch-keys','Hangul,Shift+space,Control+space'); Gio.Settings.sync()
        assert bus.set_global_engine('hangul')
        win=Gtk.Window(title='Isolated Hangul Composition Probe')
        entry=Gtk.Entry(); win.add(entry); win.show_all(); entry.grab_focus()
        import gi.repository.GdkX11
        xid=win.get_window().get_xid()
        result={}
        def type_keys():
            subprocess.run(['xdotool','windowfocus','--sync',str(xid)],check=True)
            subprocess.run(['xdotool','key','Escape'],check=True)
            subprocess.run(['xdotool','type','--delay','70','abc '],check=True)
            GLib.timeout_add(650, hangul)
            return False
        def hangul():
            result['latin_before']=entry.get_text()
            subprocess.run(['xdotool','key','Hangul'],check=True)
            subprocess.run(['xdotool','type','--delay','70','rkskek '],check=True)
            GLib.timeout_add(650, finish)
            return False
        def finish():
            result['after_hangul']=entry.get_text()
            print(json.dumps(result,ensure_ascii=False),flush=True)
            Gtk.main_quit(); return False
        GLib.timeout_add(1000,type_keys)
        GLib.timeout_add_seconds(12,lambda:(Gtk.main_quit(),False)[1])
        Gtk.main()
        assert result.get('latin_before')=='abc ',result
        assert result.get('after_hangul')=='abc 가나다 ',result
    finally:
        daemon.terminate()
        try: daemon.wait(timeout=3)
        except subprocess.TimeoutExpired: daemon.kill(); daemon.wait()

if '--worker' in sys.argv:
    worker()
else:
    with tempfile.TemporaryDirectory(prefix='ibus-keyboard-probe-') as tmp:
        log=open(Path(tmp)/'xvfb.log','w')
        x=subprocess.Popen(['Xvfb','-displayfd','1','-screen','0','640x480x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=log,text=True)
        try:
            with selectors.DefaultSelector() as sel:
                sel.register(x.stdout,selectors.EVENT_READ)
                assert sel.select(5)
                display=':'+x.stdout.readline().strip()
            Path(tmp+'/runtime').mkdir(mode=0o700)
            env={**os.environ,'XDG_RUNTIME_DIR':tmp+'/runtime','GIO_USE_VFS':'local','GTK_USE_PORTAL':'0','NO_AT_BRIDGE':'1','DISPLAY':display,'XDG_CONFIG_HOME':tmp+'/config','XDG_CACHE_HOME':tmp+'/cache','IBUS_ADDRESS':'unix:path='+tmp+'/ibus.sock','GTK_IM_MODULE':'ibus','QT_IM_MODULE':'ibus','XMODIFIERS':'@im=ibus'}
            for key in ('XAUTHORITY','DBUS_SESSION_BUS_ADDRESS'): env.pop(key,None)
            subprocess.run(['dbus-run-session','--','/usr/bin/python3',__file__,'--worker'],env=env,check=True,timeout=25)
        finally:
            x.terminate(); x.wait(timeout=3); log.close()
