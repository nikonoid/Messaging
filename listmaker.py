#!/usr/bin/python2
'''
listmaker
search for tracks and add them to a list which can be saved
as an xxpf file
'''
import pygtk
import gtk
import gobject
import pango
import psycopg2
import gst
import pygst
import threading
import thread
import os
import time
import ConfigParser
from lxml import etree

#get variables from config file
config = ConfigParser.SafeConfigParser()
config.read('/usr/local/etc/threedradio.conf')

dir_pl3d = config.get('Paths', 'dir_pl3d')
dir_mus = config.get('Paths', 'dir_mus')
dir_img = config.get('Paths', 'dir_img')
logo = config.get('Images', 'logo')

query_limit = config.getint('Listmaker', 'query_limit')

pg_user = config.get('Listmaker', 'pg_user')
pg_password = config.get('Listmaker', 'pg_password')
pg_server = config.get('Common', 'pg_server')
pg_cat_database = config.get('Common', 'pg_cat_database')


#lists 
select_items = (
    "cd.title",
    "cdtrack.trackid",
    "cdtrack.cdid",
    "cdtrack.tracknum",
    "cdtrack.tracktitle",
    "cdtrack.trackartist",
    "cd.artist",
    "cd.company",
    "cdtrack.tracklength"
    )

where_items = (
    "trackartist",
    "tracktitle",
    "cd.title",
    "cd.artist"
    )


        
class Preview_Player:
    '''
    adapted from Benny Malev's DamnSimplePlayer
    '''
    def __init__(self, time_label, hscale, reset_playbutton):
        self.player = gst.element_factory_make("playbin", "player")
        fakesink = gst.element_factory_make("fakesink", "fakesink")
        sink_pre = gst.element_factory_make("alsasink", "preview_sink")
        #sink_pre.set_property("device", "preview")
        self.player.set_property("video-sink", fakesink)
        self.player.set_property("audio-sink", sink_pre)
        bus = self.player.get_bus()
        bus.add_signal_watch()
        bus.connect("message", self.on_message)
        
        self.time_format = gst.Format(gst.FORMAT_TIME)
        
        #set statusbar ref.
        self.time_label = time_label
        self.hscale = hscale
        self.reset_playbutton = reset_playbutton
        
        #to hold place on change event in gui
        self.place_in_file = None
        self.progress_updatable = True
       
    def set_place_in_file(self,place_in_file):
        self.place_in_file = place_in_file
    
    def start(self, filepath):
        self.player.set_property("uri", "file://" + filepath)
        self.player.set_state(gst.STATE_PLAYING)
        self.play_thread_id = thread.start_new_thread(self.play_thread, ())
             
    def stop(self):
        self.play_thread_id = None
        self.player.set_state(gst.STATE_NULL)
        self.reset_components()
        
    def pause(self):
        self.player.set_state(gst.STATE_PAUSED)
                        
    def on_message(self, bus, message):
        t = message.type
        if t == gst.MESSAGE_EOS:
            self.play_thread_id = None
            self.player.set_state(gst.STATE_NULL)
            self.reset_components()
                        
        elif t == gst.MESSAGE_ERROR:
            self.play_thread_id = None
            self.player.set_state(gst.STATE_NULL)
            err, debug = message.parse_error()
            print ("Error: {0}").format (err, debug)
            self.reset_components()

    def convert_ns(self, time_int):
        s,ns = divmod(time_int, 1000000000)
        m,s = divmod(s, 60)

        if m < 60:
            str_dur = "%02i:%02i" %(m,s)
            return str_dur
        else:
            h,m = divmod(m, 60)
            str_dur = "%i:%02i:%02i" %(h,m,s)
            return str_dur
        
    def get_duration(self):
        dur_int = self.player.query_duration(self.time_format, None)[0]
        return self.convert_ns(dur_int)
        
    def set_updateable_progress(self,flag):
        self.progress_updatable = flag 
        
    def rewind_callback(self):
        pos_int = self.player.query_position(self.time_format, None)[0]
        seek_ns = pos_int - (10 * 1000000000)
        self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH, seek_ns)
        
    def forward_callback(self):
        pos_int = self.player.query_position(self.time_format, None)[0]
        seek_ns = pos_int + (10 * 1000000000)
        self.player.seek_simple(self.time_format, gst.SEEK_FLAG_FLUSH, seek_ns)
        
    def get_state(self):
        play_state = self.player.get_state(1)[1]
        #for item in play_state:
        #    print(item)
        return play_state
        
    #duration updating func
    def play_thread(self):
        play_thread_id = self.play_thread_id
        
        while play_thread_id == self.play_thread_id:
            try:
                time.sleep(0.2)
                dur_int = self.player.query_duration(self.time_format, None)[0]
                dur_str = self.convert_ns(dur_int)

                self.duration_time = dur_int / 1000000000
                
                gtk.gdk.threads_enter()
                self.time_label.set_text("00:00 / " + dur_str)
                
                #set hscale
                self.hscale.set_range(0,self.duration_time)
                
                gtk.gdk.threads_leave()
                break
            except:
                pass
                
        time.sleep(0.2)
        while play_thread_id == self.play_thread_id:
            
            #update position
            if self.place_in_file:
                self.player.seek_simple(self.time_format ,gst.SEEK_FLAG_FLUSH | gst.SEEK_FLAG_KEY_UNIT | gst.SEEK_TYPE_SET ,self.place_in_file*1000000000)
                self.place_in_file = None
                #let the seek enough time to complete
                time.sleep(0.1)
            
            pos_int = self.player.query_position(self.time_format, None)[0]
            pos_str = self.convert_ns(pos_int)
            
            self.current_time = pos_int / 1000000000
            
            if play_thread_id == self.play_thread_id:
                gtk.gdk.threads_enter()
                
                if self.progress_updatable:
                    #update hscale
                    self.hscale.set_value(self.current_time)
                
                self.time_label.set_text(pos_str + " / " + dur_str)
                
                gtk.gdk.threads_leave()
            time.sleep(1)
    def reset_components(self):  
        self.time_label.set_text("00:00 / 00:00")
        self.hscale.set_value(0)
        self.reset_playbutton()

class List_Maker():
    
    def delete_event(self, widget, event, data=None):
        return False

    def destroy(self, widget, data=None):
        gtk.main_quit()

    def main(self):
        self.window = gtk.Window(gtk.WINDOW_TOPLEVEL) 
        self.window.set_position(gtk.WIN_POS_CENTER)
        filepath_logo = dir_img + logo
        self.window.set_icon_from_file(filepath_logo)
        self.window.set_resizable(False)
        self.window.set_size_request(1100, 800)
        self.window.set_title("Listmaker")
        
        
        ###   create containers - boxes and scrolled windows  ###        
        #hpane to hold playlist and search panes
        #hpane = gtk.HPaned()
        # hbox for music catalogue
        hbox_cat = gtk.HBox(False, 5)
        # vbox for catalogue search
        vbox_cat_search = gtk.VBox(False, 5)
        # table for music catalogue search
        table_cat = gtk.Table(20, 2, False)
        # hbox for catalogue creator selection
        hbox_cat_creator = gtk.HBox(False, 5)
        # hbox for catalogue order selection
        hbox_cat_order = gtk.HBox(False, 5)
        
        # vbox for catalogue list
        vbox_cat_lst = gtk.VBox(False, 0)
        # scrolled window for catalogue list treeview
        sw_cat_lst = gtk.ScrolledWindow()
        sw_cat_lst.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_cat_lst.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC) 
        
        # hbox for preview player buttons
        hbox_pre_btn = gtk.HBox(False, 0)  
        hbox_pre_btn.set_size_request(280, 30)
        # vbox for playlist
        vbox_pl = gtk.VBox(False, 5)
        # hbox for list option buttons in the playlist
        hbox_pl = gtk.HBox(False, 0)        
        
        # scrolled holder for the playlist treelist
        sw_pl = gtk.ScrolledWindow()
        sw_pl.set_shadow_type(gtk.SHADOW_ETCHED_IN)
        sw_pl.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
 
        # hbox for Total Time 
        hbox_pl_time = gtk.HBox(False, 0)    
        hbox_pl_time.set_size_request(280, 30)


        ### Styles ###

        header_font = pango.FontDescription("Sans Bold 18")
        subheader_font = pango.FontDescription("Sans Bold 14")
        subheader_font_1 = pango.FontDescription("Sans Bold 12")
        subheader_font_2 = pango.FontDescription("Sans Bold 11")  


        ### ----------------Music Catalogue Search ---------------- ###
        
        label_cat = gtk.Label(" Music Catalogue ")
        label_cat.modify_font(header_font)        
        sep_cat_0 = gtk.HSeparator()
        label_cat_simple = gtk.Label("Simple Search")
        label_cat_simple.modify_font(subheader_font_1)
        self.entry_cat_simple = gtk.Entry(50)
        btn_cat_simple = gtk.Button("Search")
        btn_cat_simple.set_tooltip_text("Simple search")
        btn_cat_simple.set_size_request(80, 30)
        self.label_result_simple = gtk.Label()
        self.label_result_simple.set_size_request(80, 40)
        sep_cat_1 = gtk.HSeparator()
        label_cat_adv = gtk.Label("Advanced Search")
        label_cat_adv.modify_font(subheader_font_1)
        label_cat_artist = gtk.Label("Artist")
        self.entry_cat_artist = gtk.Entry(50)
        label_cat_album = gtk.Label("Album")
        self.entry_cat_album = gtk.Entry(50)
        label_cat_title = gtk.Label("Title")
        self.entry_cat_title = gtk.Entry(50)
        label_cat_cmpy = gtk.Label("Company")
        self.entry_cat_cmpy = gtk.Entry(50)
        label_cat_genre = gtk.Label("Genre")
        self.entry_cat_genre = gtk.Entry(50)        
        label_cat_com = gtk.Label("Comments")
        self.entry_cat_com = gtk.Entry(50)
        label_cat_creator = gtk.Label("Created by")
        self.cb_cat_creator = gtk.combo_box_new_text()
        self.cb_creator_add()       
        self.chk_cat_comp = gtk.CheckButton("Compilation", True)
        self.chk_cat_demo = gtk.CheckButton("Demo", True)
        self.chk_cat_local = gtk.CheckButton("Local", True)       
        self.chk_cat_fem = gtk.CheckButton("Female", True)
        label_cat_order = gtk.Label("Order by")
        self.cb_cat_order = gtk.combo_box_new_text()
        self.cb_order_add()
        btn_cat_adv = gtk.Button("Search")
        btn_cat_adv.set_tooltip_text("Advanced Search")
        self.label_result_adv = gtk.Label()
        self.label_result_adv.set_size_request(80, 40)

        ### ----------- Search Results Section -----------###

        label_results = gtk.Label("Search Results")
        label_results.modify_font(subheader_font_1)
        label_results.set_size_request(80, 30)

        #make the list
        self.store_cat = gtk.TreeStore(str ,str ,str ,str ,str ,str ,str, int)
        self.treeview_cat = gtk.TreeView(self.store_cat)
        self.treeview_cat.set_rules_hint(True)
        treeselection_cat = self.treeview_cat.get_selection()
        self.add_cat_columns(self.treeview_cat)
        
        
        ### ------------ Preview Section ------------  ###
        
        ### images for buttons
        self.image_play = gtk.Image()
        self.image_play.set_from_stock(gtk.STOCK_MEDIA_PLAY, gtk.ICON_SIZE_BUTTON)
        self.image_play.set_name("play")
        self.image_pause = gtk.Image()
        self.image_pause.set_from_stock(gtk.STOCK_MEDIA_PAUSE, gtk.ICON_SIZE_BUTTON)
        self.image_pause.set_name("pause")
        image_stop = gtk.Image()
        image_stop.set_from_stock(gtk.STOCK_MEDIA_STOP, gtk.ICON_SIZE_BUTTON)
        # preview player buttons
        self.btn_pre_play_pause = gtk.Button()
        self.btn_pre_play_pause.set_image(self.image_play)
        btn_pre_stop = gtk.Button()
        btn_pre_stop.set_image(image_stop)
        btn_pre_stop.connect("clicked", self.on_stop_clicked)
        #Label of track to preview
        self.str_dur="00:00"
        self.label_pre_time = gtk.Label("00:00 / 00:00")        
        #both lambdas toggle progressbar to be not updatable by player_pre while valve is dragged
        self.progress_pressed = lambda widget, param: self.player_pre.set_updateable_progress(False)

        self.hscale_pre = gtk.HScale()
        self.hscale_pre.set_size_request(180, 20)
        self.hscale_pre.set_range(0, 100)
        self.hscale_pre.set_increments(1, 10)
        self.hscale_pre.set_digits(0)
        self.hscale_pre.set_draw_value(False)
        self.hscale_pre.set_update_policy(gtk.UPDATE_DISCONTINUOUS) 


        # the preview player
        self.player_pre = Preview_Player(
            self.label_pre_time, self.hscale_pre, self.reset_playbutton)

        ### ---------- Playlist Section ---------- ###
        
        self.changed = False
        label_pl = gtk.Label("Playlist")
        label_pl.modify_font(subheader_font_1)
        label_pl.set_size_request(80, 30)     
        
        btn_inf = gtk.Button("Info")
        btn_inf.set_tooltip_text("Information about the selected track")
        btn_rem = gtk.Button("Remove")
        btn_rem.set_tooltip_text("Remove the selected track from the playlist")
        btn_open = gtk.Button("_Open")
        btn_open.set_tooltip_text("Open a new playlist")
        btn_save = gtk.Button("_Save")
        btn_save.set_tooltip_text("Save this playlist")
        btn_saveas = gtk.Button("Save As")
        btn_saveas.set_tooltip_text("Save this playlist as a new file with a different name")
        
        
        self.store_pl = gtk.ListStore(str ,str ,str ,str ,str ,str ,str, str)
        self.treeview_pl = gtk.TreeView(self.store_pl)
        self.treeview_pl.set_rules_hint(True)
        treeselection_pl = self.treeview_pl.get_selection()
        self.add_pl_columns(self.treeview_pl)        
        
        label_time_0 = gtk.Label("Playlist Total Time - ")
        self.label_time_1 = gtk.Label("00:00  ")

        ### dnd and connections ###
        self.treeview_cat.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_pl.enable_model_drag_source(gtk.gdk.BUTTON1_MASK, 
                                              [("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_pl.enable_model_drag_dest([("copy-row", 0, 0)], 
                                              gtk.gdk.ACTION_COPY)
        self.treeview_cat.connect("drag_data_get", self.cat_drag_data_get_data)
        self.treeview_pl.connect("drag_data_get", self.pl_drag_data_get_data)
        self.treeview_pl.connect("drag_data_received",
                              self.drag_data_received_data)

        self.window.connect("delete_event", self.delete_event)
        self.window.connect("destroy", self.destroy)
        treeselection_cat.connect('changed', self.cat_selection_changed)
        btn_cat_simple.connect("clicked", self.simple_search)
        self.entry_cat_simple.connect("activate", self.simple_search)
        self.entry_cat_artist.connect("activate", self.advanced_search)
        self.entry_cat_album.connect("activate", self.advanced_search)
        self.entry_cat_title.connect("activate", self.advanced_search)
        self.entry_cat_cmpy.connect("activate", self.advanced_search)
        self.entry_cat_genre.connect("activate", self.advanced_search)
        self.entry_cat_com.connect("activate", self.advanced_search)       
        btn_cat_adv.connect("clicked", self.advanced_search)
        self.btn_pre_play_pause.connect("clicked", self.play_pause_clicked)
        btn_pre_stop.connect("clicked", self.on_stop_clicked)
        self.hscale_pre.connect("button-release-event", self.on_seek_changed)
        self.hscale_pre.connect("button-press-event", self.progress_pressed)
        btn_inf.connect("clicked", self.info_row)
        btn_rem.connect("clicked", self.remove_row)
        btn_open.connect("clicked", self.open_dialog)
        btn_save.connect("clicked", self.save)
        btn_saveas.connect("clicked", self.saveas)
        
        ### do the packing ###

        hbox_pre_btn.pack_start(self.btn_pre_play_pause, False)
        hbox_pre_btn.pack_start(btn_pre_stop, False)
        hbox_pre_btn.pack_start(self.hscale_pre, True)
        hbox_pre_btn.pack_start(self.label_pre_time, True)   

        table_cat.attach(label_cat_artist, 0, 1, 0, 1, False, False, 5, 0)
        table_cat.attach(self.entry_cat_artist, 1, 2, 0, 1, False, False, 5, 0)
        table_cat.attach(label_cat_album, 0, 1, 1, 2, False, False, 5, 0)
        table_cat.attach(self.entry_cat_album, 1, 2, 1, 2, False, False, 5, 0)
        table_cat.attach(label_cat_title, 0, 1, 2, 3, False, False, 5, 0)
        table_cat.attach(self.entry_cat_title, 1, 2, 2, 3, False, False, 5, 0)
        table_cat.attach(label_cat_cmpy, 0, 1, 3, 4, False, False, 5, 0)
        table_cat.attach(self.entry_cat_cmpy, 1, 2, 3, 4, False, False, 5, 0)
        table_cat.attach(label_cat_com, 0, 1, 4, 5, False, False, 5, 0)
        table_cat.attach(self.entry_cat_com, 1, 2, 4, 5, False, False, 5, 0)
        table_cat.attach(label_cat_genre, 0, 1, 5, 6, False, False, 5, 0)
        table_cat.attach(self.entry_cat_genre, 1, 2, 5, 6, False, False, 5, 0)
        
        
        hbox_cat_creator.pack_start(label_cat_creator, False)
        hbox_cat_creator.pack_start(self.cb_cat_creator, False)
        hbox_cat_order.pack_start(label_cat_order, False)
        hbox_cat_order.pack_start(self.cb_cat_order, False)

        vbox_cat_search.pack_start(sep_cat_0, False)
        vbox_cat_search.pack_start(label_cat_simple, False)
        vbox_cat_search.pack_start(self.entry_cat_simple, False)
        vbox_cat_search.pack_start(btn_cat_simple, False)
        vbox_cat_search.pack_start(self.label_result_simple, False)
        vbox_cat_search.pack_start(sep_cat_1, False)
        vbox_cat_search.pack_start(label_cat_adv, False)
        
        vbox_cat_search.pack_start(table_cat, False)
        
        vbox_cat_search.pack_start(hbox_cat_creator, False)
        
        vbox_cat_search.pack_start(self.chk_cat_comp, False)
        vbox_cat_search.pack_start(self.chk_cat_demo, False)
        vbox_cat_search.pack_start(self.chk_cat_local, False)
        vbox_cat_search.pack_start(self.chk_cat_fem, False)
        #vbox_cat_search.pack_start(hbox_cat_order, False)   
        vbox_cat_search.pack_start(btn_cat_adv, False)
        #vbox_cat_search.pack_start(self.entry_cat_adv, False)  
        vbox_cat_search.pack_start(self.label_result_adv, False)
        sw_cat_lst.add(self.treeview_cat)
        sw_pl.add(self.treeview_pl)   
        vbox_cat_lst.pack_start(label_results, False)
        vbox_cat_lst.pack_start(sw_cat_lst, True)
        vbox_cat_lst.pack_start(hbox_pre_btn, False)



        hbox_pl_time.pack_end(self.label_time_1, False)
        hbox_pl_time.pack_end(label_time_0, False)
                
        hbox_pl.pack_start(btn_inf, False)
        hbox_pl.pack_start(btn_rem, False)
        hbox_pl.pack_start(btn_open, False)
        hbox_pl.pack_start(btn_save, False)
        hbox_pl.pack_start(btn_saveas, False)
        
        vbox_pl.pack_start(label_pl, False)
        vbox_pl.pack_start(hbox_pl, False)
        vbox_pl.pack_start(sw_pl, True)
        vbox_pl.pack_start(hbox_pl_time, False)
        hbox_cat.pack_start(vbox_cat_search, False)  
        hbox_cat.pack_start(vbox_cat_lst, True) 
        hbox_cat.pack_start(vbox_pl, False)  
        #hpane.pack1(hbox_cat, False, False)
        #hpane.pack2(vbox_pl, False, False)
        #window.add(hpane)
        self.window.add(hbox_cat)
        self.window.show_all()
        
        gtk.gdk.threads_init()
        
        self.Saved = False
        self.pl3d_file = None

        gtk.main()

    # columns for the lists
    def add_cat_columns(self, treeview):        
        #Column ONE
        column = gtk.TreeViewColumn('Album / Title', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        #column.set_visible(False)
        column.set_max_width(360)
        column.set_resizable(True)
        treeview.append_column(column)
        # column TWO
        column = gtk.TreeViewColumn('Code', gtk.CellRendererText(),
                                     text=1)
        column.set_sort_column_id(1)
        column.set_visible(False)
        treeview.append_column(column)

        # column THREE
        column = gtk.TreeViewColumn('CD Code/Track No', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_visible(False)
        treeview.append_column(column)

        # column FOUR
        column = gtk.TreeViewColumn('Album', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        column.set_resizable(True)
        column.set_visible(False)

        treeview.append_column(column)
        
        #Column FIVE
        column = gtk.TreeViewColumn('Artist', gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        column.set_resizable(True)
        treeview.append_column(column)
                
        #Column SIX
        column = gtk.TreeViewColumn('Company', gtk.CellRendererText(),
                                    text=5)
        column.set_sort_column_id(5)
        column.set_visible(False)
        treeview.append_column(column)
        
        #Column SEVEN
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                    text=6)
        column.set_sort_column_id(6)
        #column.set_visible(False)
        treeview.append_column(column)
        
        #Column EIGHT
        column = gtk.TreeViewColumn('TrackTime - int', gtk.CellRendererText(),
                                    text=7)
        column.set_sort_column_id(7)
        column.set_visible(False)
        treeview.append_column(column) 
        
    def add_pl_columns(self, treeview):
        column = gtk.TreeViewColumn('Title', gtk.CellRendererText(),
                                    text=0)
        column.set_sort_column_id(0)
        #column.set_visible(False)
        #column.set_max_width(360)
        column.set_resizable(True)
        treeview.append_column(column)
        # column TWO
        column = gtk.TreeViewColumn('Code', gtk.CellRendererText(),
                                     text=1)
        column.set_sort_column_id(1)
        column.set_visible(False)
        column.set_clickable(False)

        treeview.append_column(column)

        # column THREE
        column = gtk.TreeViewColumn('CD Code/Track No', gtk.CellRendererText(),
                                    text=2)
        column.set_sort_column_id(2)
        column.set_visible(False)
        treeview.append_column(column)

        # column FOUR
        column = gtk.TreeViewColumn('Album', gtk.CellRendererText(),
                                    text=3)
        column.set_sort_column_id(3)
        column.set_clickable(False)
        column.set_resizable(True)
        column.set_visible(False)

        treeview.append_column(column)
        
        #Column FIVE
        column = gtk.TreeViewColumn('Artist', gtk.CellRendererText(),
                                    text=4)
        column.set_sort_column_id(4)
        column.set_clickable(False)
        column.set_resizable(True)
        column.set_visible(False)

        treeview.append_column(column)
                
        #Column SIX
        column = gtk.TreeViewColumn('Company', gtk.CellRendererText(),
                                    text=5)
        column.set_sort_column_id(5)
        column.set_visible(False)
        treeview.append_column(column)
        
        #Column SEVEN
        column = gtk.TreeViewColumn('Time', gtk.CellRendererText(),
                                    text=6)
        column.set_sort_column_id(6)
        column.set_clickable(False)
        treeview.append_column(column)
        
        #Column EIGHT
        column = gtk.TreeViewColumn('TrackTime - int', gtk.CellRendererText(),
                                    text=7)
        column.set_sort_column_id(7)
        column.set_visible(False)
        treeview.append_column(column) 

    # dnd    
    def cat_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        tuple_data = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7)
        str_data = str(tuple_data).strip('[]')
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, str_data)

    def pl_drag_data_get_data(self, treeview, context, selection, target_id,
                           etime):
        treeselection = treeview.get_selection()
        model, iter = treeselection.get_selected()
        datatuple = model.get(iter, 0, 1, 2, 3, 4, 5, 6, 7)
        datastring = str(datatuple).strip('[]')
        selection.set(gtk.gdk.SELECTION_TYPE_STRING, 8, datastring)
        model.remove(iter)
        
    def drag_data_received_data(self, treeview, context, x, y, selection,
                                info, etime):
        model = treeview.get_model()
        str_data = selection.get_text()       
        tuple_data = eval(str_data)
        list_data = list(tuple_data)
        track_id = list_data[1]
        int_time = list_data[7]
        ID = list_data[2]

        if track_id and  int_time:
            filepath = self.get_filepath(ID)
            if not filepath:
                str_error = "Unable to add to the list, file does not exist. That track has probably not yet been ripped into the music store"
                self.error_dialog(str_error) 
            else:
                drop_info = treeview.get_dest_row_at_pos(x, y)
                if drop_info:
                    path, position = drop_info
                    iter = model.get_iter(path)
                    if (position == gtk.TREE_VIEW_DROP_BEFORE
                        or position == gtk.TREE_VIEW_DROP_INTO_OR_BEFORE):
                        model.insert_before(iter, list_data)
                        #self.join_drop(model, iter, True)

                    else:
                        model.insert_after(iter, list_data)
                        #self.join_drop(model, iter, False)
                        
                else:
                    model.append(list_data)
                if context.action == gtk.gdk.ACTION_MOVE:
                    context.finish(True, True, etime)
                
                self.update_time_total()
                self.changed = True
                    
        else:
            str_error = "Unable to add to the list. That track has probably not yet been ripped into the music store"
            self.error_dialog(str_error)


        return

    # music catalogue section       
    def pg_connect_cat(self):
        conn_string = 'dbname={0} user={1} host={2} password={3}'.format (
            pg_cat_database, pg_user, pg_server, pg_password)
        conn = psycopg2.connect(conn_string)
        #cur = conn.cursor()
        return conn

    def simple_search(self, widget):
        result = self.query_simple()
        simple = True
        if result:
            self.length_check(result)
            self.add_to_cat_store(result)
            int_res = len(result)
           
        else:
            self.clear_cat_list()
            int_res = 0
        
        self.update_result_label(int_res, simple)
                                
    def query_simple(self):    
        str_error_none = "No search terms were entered"
        str_error_len = "Please enter more than three characters in your search"
            
        searchitem = self.entry_cat_simple.get_text()
        if not searchitem:
            self.error_dialog(str_error_none)
            return False
            
        if len(searchitem) < 3:
            self.error_dialog(str_error_len)
            return False
        
        conn = self.pg_connect_cat()

        str_select = "SELECT "
        for s in select_items:    
            str_select = str_select + s + ", "

        str_select = str_select.rstrip(", ")

        str_from = " from cdtrack inner JOIN cd on cdtrack.cdid=cd.id "
        str_where = "where "
        for s in where_items:
            str_where = str_where + s + " ilike '%" + searchitem + "%' or "

        str_where = str_where.rstrip(" or ")
        str_order = "order by cd.title, cdtrack.tracknum "
        str_limit = "LIMIT " + str(query_limit)

        query = str_select + str_from + str_where + str_order + str_limit

        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()
        
        return result

    def length_check(self, result):
        if len(result) == query_limit:
            str_warn_0 = "Warning - your query returned "
            str_warn_1 = " or more results. Only displaying the first "
            str_warn_2 = ". Please modify your search and be more specific."
            str_warn = str_warn_0 + str(query_limit) + str_warn_1 + str(query_limit) + str_warn_2
            self.warn_dialog(str_warn)

    def add_to_cat_store(self, result):
        self.clear_cat_list()
        var_album = ""
        for item in result:
            model = self.treeview_cat.get_model()
            album = item[0]
            track_id = str(item[1])
            cd_code = str(format(item[2], '07d'))
            track_no = str(format(item[3], '02d'))
            cd_track_code =  cd_code + "-" + track_no
            title = item[4]
            if item[5]:
                artist = item[5]
            else:
                artist = item[6]
            company = item[7]
            int_time = item[8]
            dur_time = self.convert_time(int_time)
            
            if not album:
                album = "(No Title)"

            
            if not album == var_album:                
                n = model.append(None, [album, None, None, None, artist, None, None, 0])
                model.append(n, [title, track_id, cd_track_code, album, artist, company, dur_time, int_time])
            else:
                model.append(n, [title, track_id, cd_track_code, album, artist, company, dur_time, int_time])
            var_album = album
            

            '''
            if not album == var_album:                
                n = model.append(None, [album, None, None, None, None, None, None, 0])
                model.append(n, [title, track_id, cd_track_code, album, artist, company, dur_time, int_time])
            else:
                model.append(n, [title, track_id, cd_track_code, album, artist, company, dur_time, int_time])
            var_album = album
            '''

    def advanced_search(self, widget):
        result = self.query_adv()
        simple = False
        if result:
            self.length_check(result)
            self.add_to_cat_store(result)
            int_res = len(result)
            
        else:
            self.clear_cat_list()
            int_res = 0
            
        self.update_result_label(int_res, simple)
    
    def query_adv(self):
        #obtain text from entries and combos
        artist = self.entry_cat_artist.get_text()
        album = self.entry_cat_album.get_text()
        title = self.entry_cat_title.get_text()
        company = self.entry_cat_cmpy.get_text()
        comments = self.entry_cat_com.get_text()
        genre = self.entry_cat_genre.get_text()
        created_by = self.cb_cat_creator.get_active_text()
        if created_by:
            ls_creator = created_by.split(',')
            created_by = ls_creator[0]
        compil = self.chk_cat_comp.get_active()
        demo = self.chk_cat_demo .get_active()
        local = self.chk_cat_local.get_active()
        female = self.chk_cat_fem.get_active()
        #query according to the text
        
        str_error_none = "No search terms were entered"
        str_error_len = "Please enter more than three characters in your search"
        
        if not artist and not album and not title and not company and not comments and not genre:
            self.error_dialog(str_error_none)
            return False
            
        for item in (artist, album, title, company, comments, genre):
            if item:
                if len(item) < 3:
                    self.error_dialog(str_error_len)
                    return False
        
        if artist:
            q_artist = "(cd.artist ILIKE '%" + artist + "%' OR cdtrack.trackartist ILIKE '%" + artist + "%') AND "
        else:
            q_artist = None
        if album:
            q_album = "cd.title ILIKE '%" + album + "%' AND "
        else:
            q_album = None
        if title:
            q_title = "cdtrack.tracktitle ILIKE '%" + title + "%' AND "
        else:
            q_title = None
        if company:
            q_company = "cd.company ILIKE '%" + company + "%' AND "
        else:
            q_company = None
        if comments:
            q_comments = "cdcomment.comment ILIKE '%" + comments + "%' AND "
        else:
            q_comments = None
        if genre:
            q_genre = "cd.genre ILIKE '%" + genre + "%' AND "
        else:
            q_genre = None
        if created_by:
            q_created_by = "cd.createwho = " + created_by + " AND "
        else:
            q_created_by = None        
        if compil:
            q_compil = "cd.compilation = 2 AND "
        else:
            q_compil = None
        if demo:
            q_demo = "cd.demo = 2 AND "
        else:
            q_demo = None
        if local:
            q_local = "cd.local = 2 AND "
        else:
            q_local = None
        if female:
            q_female = "cd.female = 2 AND "
        else:
            q_female = None
        
        str_select = "SELECT "
        for s in select_items:    
            str_select = str_select + s + ", "        
        str_select = str_select.rstrip(", ")
        str_from = " FROM cdtrack INNER JOIN cd ON cdtrack.cdid=cd.id "
        str_where = "WHERE "
        
        adv_var = (
            q_artist,
            q_album,
            q_title,
            q_company,
            q_comments,
            q_genre,
            q_created_by,
            q_compil,
            q_demo,
            q_local,
            q_female,
            )
            
        for item in adv_var:
            if item:
                str_where = str_where + item
      
        str_where = str_where.rstrip("AND ")
        
        str_order = " ORDER BY cd.title, cdtrack.tracknum "
        str_limit = "LIMIT " + str(query_limit)

        query = str_select + str_from + str_where + str_order + str_limit        

        conn = self.pg_connect_cat()
        cur = conn.cursor()
        cur.execute(query)
        result = cur.fetchall()
        cur.close()
        conn.close()        
        
        return result

    def get_creator(self):
        query = "SELECT DISTINCT cd.createwho, users.first, users.last FROM cd JOIN users ON cd.createwho = users.id ORDER BY users.last"
        conn = self.pg_connect_cat()
        cur = conn.cursor()
        cur.execute(query)
        list_creator = cur.fetchall()
        cur.close()
        conn.close()
        return list_creator

    def cb_creator_add(self):
        liststore_creator = gtk.ListStore(str)        
        list_creator = self.get_creator()
        for item in list_creator:
            str_creator = str(item[0]) + ", " + item[1] + " " + item[2]
            self.cb_cat_creator.append_text(str_creator)
        self.cb_cat_creator.prepend_text("")

    def get_order(self):
      model = self.cb_cat_order.get_model()
      active = self.cb_cat_order.get_active()
      if active < 0:
          return None
      return model[active][0]

    def cb_order_add(self):
        list_order = ["Artist Alphabetical",
            "Album Alphabetical",
            "Most recent first",
            "Oldest First"]
        for item in list_order:
            self.cb_cat_order.append_text(item)
        self.cb_cat_order.set_active(0)

    def clear_cat_list(self):
        model = self.treeview_cat.get_model()
        model.clear()

    def update_result_label(self, int_res, simple):
        if int_res < 200 :
            str_results = "Your search returned {0} results".format(int_res)
            if simple:
                self.label_result_simple.set_text(str_results)
                self.label_result_adv.set_text("")
            else:
                self.label_result_adv.set_text(str_results)
                self.label_result_simple.set_text("")  
        else:
            self.label_result_adv.set_text("")
            self.label_result_simple.set_text("")

    # preview section  
    def get_sel_filepath(self):
        treeselection = self.treeview_cat.get_selection()
        model, iter = treeselection.get_selected()
        ID = model.get(iter, 2)
        ID = ID[0]
        filepath = self.get_filepath(ID)
        if not filepath:
            str_error = "Unable to play, file does not exist. That track has probably not yet been ripped into the music store"
            self.error_dialog(str_error)
            return
        else: 
            return filepath

    def play_pause_clicked(self, widget):
        filepath = self.get_sel_filepath()
        if filepath:
            img = self.btn_pre_play_pause.get_image()
            if img.get_name() == "play":          
                self.btn_pre_play_pause.set_image(self.image_pause)
                self.player_pre.start(filepath)
                
            else:
                self.player_pre.pause()
                self.btn_pre_play_pause.set_image(self.image_play)
                
    def on_stop_clicked(self, widget):
        self.player_pre.stop()
        self.btn_pre_play_pause.set_image(self.image_play)
        self.label_pre_time.set_text("00:00 / " + self.str_dur)
    
    def reset_playbutton(self):
        self.btn_pre_play_pause.set_image(self.image_play)
        
    def cat_selection_changed(self, selection):
        playstatus = self.player_pre.get_state() 
        if (playstatus == gst.STATE_PLAYING) or (playstatus == gst.STATE_PAUSED):
            self.on_stop_clicked(True)
            
    def on_seek_changed(self, widget, param):
        self.player_pre.set_updateable_progress(True)
        self.player_pre.set_place_in_file(self.hscale_pre.get_value())
    

    # playlist section
    def update_time_total(self):
        model = self.treeview_pl.get_model()
        iter = model.get_iter_first()
        total_time = 0
        while iter:
            int_time = model.get_value(iter, 7)
            int_time = int(int_time)
            total_time = total_time + int_time
            iter = model.iter_next(iter)
        str_time = self.convert_time(total_time)
        self.label_time_1.set_text(str_time + "  ")

    def get_filename(self, act, name):
        '''
        open a file chooser window to open or save a playlist file
    
        '''

        if act == "open_file":
            action = gtk.FILE_CHOOSER_ACTION_OPEN
            btn = gtk.STOCK_OPEN
            rsp = gtk.RESPONSE_OK
        elif act == "save_file":
            action = gtk.FILE_CHOOSER_ACTION_SAVE
            btn = gtk.STOCK_SAVE
            rsp = gtk.RESPONSE_ACCEPT
                        
        dialog = gtk.FileChooserDialog(
            "Select a Playlist",
            None,
            action,
            (gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL,
            btn, rsp)
            )

        if act == "open_file":
            dialog.set_default_response(gtk.RESPONSE_OK)

        elif act == "save_file":
            dialog.set_default_response(gtk.RESPONSE_ACCEPT)

        dialog.set_current_folder(dir_pl3d)
        dialog.set_do_overwrite_confirmation(True)
        if name:
            dialog.set_current_name(name)

        filter = gtk.FileFilter()
        filter.set_name("Playlist files")
        filter.add_pattern("*.pl3d")

        dialog.add_filter(filter)

        response = dialog.run()
        filename = dialog.get_filename()
        sfx = ".pl3d"
        
        if not filename[-5:] == sfx:
            filename = filename + sfx
   
        if response == gtk.RESPONSE_OK:
            self.open_pl(filename)
            basename = os.path.basename(filename)
            title = basename[:-5]
            self.window.set_title(title)
            self.changed = False
            
        elif response == gtk.RESPONSE_ACCEPT:
            basename = os.path.basename(filename)
            title = basename[:-5]
            self.window.set_title(title)
            try:
                self.save_pl(filename)
                self.changed = False
            except IOError:
                str_error = '''
        It looks like you are trying to overwrite 
        somebody else's playlist.

        Not Allowed!'''
                self.error_dialog(str_error)

        dialog.destroy()

    def info_row(self, widget):    
        treeselection = self.treeview_pl.get_selection()
        model, iter = treeselection.get_selected()
        try:
            datatuple = model.get(iter, 0, 4, 3, 5)
            self.info_message(datatuple)
            
        except TypeError:
            this_error = "silent"
        return   

    def info_message(self, datatuple):
        title = datatuple[0]
        artist = datatuple[1]
        album = datatuple[2]
        company = datatuple[3] 
        
        title_txt = "Title: {0}".format (title)
        artist_txt = "Artist: {0}".format (artist)
        album_txt = "Album: {0}".format (album)
        company_txt = "Company: {0}".format (company)
        
        label_title = gtk.Label(title_txt)
        label_artist = gtk.Label(artist_txt)   
        label_album = gtk.Label(album_txt)
        label_company = gtk.Label(company_txt)
           
        dialog = gtk.Dialog("Information", None, 0, (gtk.STOCK_OK, gtk.RESPONSE_OK))
        dialog.set_default_size(350, 150)

        dialog.vbox.pack_start(label_artist, True, True, 0)
        dialog.vbox.pack_start(label_title, True, True, 0)
        dialog.vbox.pack_start(label_album, True, True, 0)
        dialog.vbox.pack_start(label_company, True, True, 0)
        
        dialog.show_all()
        dialog.run()
        dialog.destroy()

    def remove_row(self, widget):    
        treeselection = self.treeview_pl.get_selection()
        model, iter = treeselection.get_selected()
        if iter:
            model.remove(iter) 
            model = self.treeview_pl.get_model()
            self.changed = True
        else:
            print("Nothing selected")
        iter = model.get_iter_first()
        if iter:
            self.update_time_total()
        else:
            self.label_time_1.set_text("00:00  ")

    def get_tracklist(self):
        model = self.treeview_pl.get_model()
        iter = model.get_iter_first()
        ls_tracklist = []
        while iter:
            row = model.get(iter, 0, 1, 2, 3, 4, 5, 7)
            ls_tracklist.append(row)
            iter = model.iter_next(iter)

        return ls_tracklist
            
    def open_dialog(self, widget):
        '''
        simply open a playlist - or
        check if there is a changed playlist open and ask if you want to save 
        it before opening another
        '''
        action = "open_file"
        if self.changed:
            self.save_change()
        self.get_filename(action, None)

    def save_change(self):
        dialog = gtk.Dialog("Save List?", None, 0, 
        (gtk.STOCK_OK, gtk.RESPONSE_OK, 
         gtk.STOCK_CANCEL, gtk.RESPONSE_CANCEL))
        
        ask_save = '''
        Do you want to save the changes that you made to this list 
        before you open another one?
        
        Click 'OK' to save 
        Or click 'Cancel' to open a new list without saving this one
        '''
        
        label_save = gtk.Label(ask_save)
        dialog.vbox.pack_start(label_save, True, True, 0)
        dialog.show_all()
        
        
        response = dialog.run()
        if response == gtk.RESPONSE_OK:
            self.save(None)
        dialog.destroy()

        
    def open_pl(self, filename):
        if filename:
            ls_tracklist = self.pl3d2pylist(filename)
            model = self.treeview_pl.get_model()
            model.clear()
            for item in ls_tracklist:
                title = item[0]
                
                #identifier is the track ID within a URL
                #eg http://threedradio.com/1234
                identifier = item[1]
                if identifier:
                    track_id = os.path.split(identifier)[1]
                
                #location is the filepath. It contains the track number and CD ID 
                location = item[2]
                if location:
                    f_splitext = os.path.splitext(location)[0]
                    ID = os.path.split(f_splitext)[1]
                
                album = item[3]
                creator = item[4]
                
                #the annotation element is used to hold the company name
                annotation = item[5]
                company = annotation
                
                #duration is in milliseconds
                duration = item[6]
                if duration:
                    int_dur = int(duration)/1000
                    str_dur = self.convert_time(int_dur)
                
                row = (title, track_id, ID, album, creator, company, str_dur, int_dur)
                model.append(row)
            
            self.update_time_total()
            self.pl3d_file = filename
                        
    def save(self, widget):
        if self.pl3d_file:
            filename = self.pl3d_file
            ls_tracklist = self.get_tracklist()
            doc = self.pylist2pl3d(ls_tracklist)
            try:
                doc.write(filename, pretty_print=True)
                self.Saved = True
            except IOError:
                self.saveas(None) 
                self.Saved = True

        else:
            action = "save_file"
            self.get_filename(action, 'Untitled.pl3d')
            
    def saveas(self, widget):
        action = "save_file"
        name = "Untitled.pl3d"
        self.get_filename(action, name)
        
    def save_pl(self, filename):
        '''
        Called from the get_filename function to do the saving of the 
        list to the pl3d file
        '''
        ls_tracklist = self.get_tracklist()
        doc = self.pylist2pl3d(ls_tracklist)
        doc.write(filename, pretty_print=True)
        self.pl3d_file = filename
        self.Saved = True
                
    def pylist2pl3d(self, ls_tracklist):
        '''
        write the track information in the list to a pl3d file
        '''
        pl3d_ns = "http://xspf.org/ns/0/"
        ns = "{%s}" % pl3d_ns
        pl3d_nsmap = {None : pl3d_ns}
        playlist = etree.Element(ns + "playlist", version="1.0", nsmap=pl3d_nsmap)
        trackList = etree.SubElement(playlist, ns + "trackList")

        for ls_track in ls_tracklist:
            track = etree.SubElement(trackList, ns + "track")        
            title = etree.SubElement(track, ns + "title")
            identifier = etree.SubElement(track, ns + "identifier")
            location = etree.SubElement(track, ns + "location")
            album = etree.SubElement(track, ns + "album")
            creator = etree.SubElement(track, ns + "creator")
            annotation = etree.SubElement(track, ns + "annotation")
            duration = etree.SubElement(track, ns + "duration")
     
            title.text = ls_track[0]
            identifier.text = ls_track[1]                        
            location.text = ls_track[2]
            album.text = ls_track[3]
            creator.text = ls_track[4]
            annotation.text = ls_track[5]
            duration.text = str(int(ls_track[6])*1000)

        pl3dfile = etree.tostring(playlist, pretty_print=True)
        doc = etree.ElementTree(playlist)
        return doc

    def pl3d2pylist(self, filename):
        '''
        convert the information in an pl3d file to a python list
        '''
        doc = etree.parse(filename)
        #print(etree.tostring(doc, pretty_print=True))

        pl3d_ns = "http://xspf.org/ns/0/"
        ns = "{%s}" % pl3d_ns

        el_tracklist = doc.findall("//%strack" % ns)

        ls_tracklist = []

        for track in el_tracklist:

            if track.find("%stitle" % ns) is not None:
                str_title = track.find("%stitle" % ns).text
            else:
                str_title = None
                
            if track.find("%sidentifier" % ns) is not None:
                str_identifier = track.find("%sidentifier" % ns).text
            else:
                str_identifier = None
                
            if track.find("%slocation" % ns) is not None:
                str_location = track.find("%slocation" % ns).text
            else:
                str_location = None

            if track.find("%salbum" % ns) is not None:
                str_album = track.find("%salbum" % ns).text
            else:
                str_album = None     
                           
            if track.find("%screator" % ns) is not None:
                str_creator = track.find("%screator" % ns).text
            else:
                str_creator = None
                
            if track.find("%sannotation" % ns) is not None:
                str_annotation = track.find("%sannotation" % ns).text
            else:
                str_annotation = None

            if track.find("%sduration" % ns) is not None:
                str_duration = track.find("%sduration" % ns).text
            else:
                str_duration = None

            tp_track = (
                str_title, 
                str_identifier, 
                str_location, 
                str_album, 
                str_creator, 
                str_annotation, 
                str_duration
                )
                
            ls_tracklist.append(tp_track)
            
        return ls_tracklist



    #common functions
    def convert_time(self, dur):
        s = int(dur)
        m,s = divmod(s, 60)

        if m < 60:
            str_dur = "%02i:%02i" %(m,s)
            return str_dur
        else:
            h,m = divmod(m, 60)
            str_dur = "%i:%02i:%02i" %(h,m,s)
            return str_dur   

    def get_filepath(self, ID):
        filename = ID + ".mp3"
        dir_cd = ID[0:-3] + "/"
        filepath = dir_mus + dir_cd + filename
        print(filepath)
        if not os.path.isfile(filepath):
            return False
        else:
            return filepath

    # message dialogs
    def warn_dialog(self, str_warn):
        m = gtk.MessageDialog(None, 0, 
                    gtk.MESSAGE_WARNING, gtk.BUTTONS_OK, 
                    str_warn)
        m.run()
        m.destroy()
    
    def error_dialog(self, str_error):
        messagedialog = gtk.MessageDialog(None, 0, 
                    gtk.MESSAGE_ERROR, gtk.BUTTONS_OK, 
                    str_error)
        messagedialog.run()
        messagedialog.destroy()  

    
lm = List_Maker()
lm.main()
        
'''
Feature request
Tooltip over list to show artist name

'''