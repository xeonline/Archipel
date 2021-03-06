# 
# archipelHypervisor.py
# 
# Copyright (C) 2010 Antoine Mercadal <antoine.mercadal@inframonde.eu>
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
# 
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""
Contains TNArchipelVirtualMachines, the entities uses for hypervisor

This provides the possibility to instanciate TNArchipelVirtualMachines
"""
import xmpp
import sys
import socket
import sqlite3
import datetime
import commands
import time
from threading import Thread
from utils import *
from archipelEntity import *
from archipelVirtualMachine import *
import string
import random
import libvirt

ARCHIPEL_ERROR_CODE_HYPERVISOR_ALLOC            = -9001
ARCHIPEL_ERROR_CODE_HYPERVISOR_FREE             = -9002
ARCHIPEL_ERROR_CODE_HYPERVISOR_ROSTER           = -9003
ARCHIPEL_ERROR_CODE_HYPERVISOR_CLONE            = -9004
ARCHIPEL_ERROR_CODE_HYPERVISOR_IP               = -9005
ARCHIPEL_ERROR_CODE_HYPERVISOR_LIBVIRT_URI      = -9006
ARCHIPEL_ERROR_CODE_HYPERVISOR_ALLOC_MIGRATION  = -9007
ARCHIPEL_ERROR_CODE_HYPERVISOR_FREE_MIGRATION   = -9008
ARCHIPEL_ERROR_CODE_HYPERVISOR_CAPABILITIES     = -9009

class TNThreadedVirtualMachine(Thread):
    """
    this class is used to run L{ArchipelVirtualMachine} main loop
    in a thread.
    """
    def __init__(self, jid, password, hypervisor, configuration, name):
        """
        the contructor of the class
        @type jid: string
        @param jid: the jid of the L{TNArchipelVirtualMachine} 
        @type password: string
        @param password: the password associated to the JID
        """
        Thread.__init__(self)
        self.jid = jid
        self.password = password
        self.xmppvm = TNArchipelVirtualMachine(self.jid, self.password, hypervisor, configuration, name)
        
    
    
    def get_instance(self):
        """
        this method return the current L{TNArchipelVirtualMachine} instance
        @rtype: ArchipelVirtualMachine
        @return: the L{ArchipelVirtualMachine} instance
        """
        return self.xmppvm
    
    
    def run(self):
        """
        overiddes sur super class method. do the L{TNArchipelVirtualMachine} main loop
        """
        self.xmppvm.connect()
        self.xmppvm.loop() 
    




class TNArchipelHypervisor(TNArchipelEntity):
    """
    this class represent an Hypervisor XMPP Capable. This is an XMPP client
    that allows to alloc threaded instance of XMPP Virtual Machine, destroy already
    active XMPP VM, and remember which have been created.
    """       
    
    def __init__(self, jid, password, configuration, name, database_file="./database.sqlite3"):
        """
        this is the constructor of the class.
        
        @type jid: string
        @param jid: the jid of the hypervisor
        @type password: string
        @param password: the password associated to the JID
        @type database_file: string
        @param database_file: the sqlite3 file to store existing VM for persistance
        """
        TNArchipelEntity.__init__(self, jid, password, configuration, name)
        
        self.virtualmachines            = {}
        self.database_file              = database_file
        self.xmppserveraddr             = self.jid.getDomain()
        self.local_libvirt_uri          = self.configuration.get("GLOBAL", "libvirt_uri")
        self.entity_type                = "hypervisor"
        self.default_avatar             = self.configuration.get("HYPERVISOR", "hypervisor_default_avatar")
        self.libvirt_event_callback_id  = None;
        
        # permissions
        permission_db_file              = self.configuration.get("HYPERVISOR", "hypervisor_permissions_database_path")
        permission_admin_name           = self.configuration.get("GLOBAL", "archipel_root_admin")
        self.permission_center          = archipelPermissionCenter.TNArchipelPermissionCenter(permission_db_file, permission_admin_name);
        self.init_permissions()
        
        names_file = open(self.configuration.get("HYPERVISOR", "name_generation_file"), 'r')
        self.generated_names = names_file.readlines();
        names_file.close();
        self.number_of_names = len(self.generated_names) - 1
        
        log.info("server address defined as {0}".format(self.xmppserveraddr))
        
        
        # hooks
        self.create_hook("HOOK_HYPERVISOR_ALLOC");
        self.create_hook("HOOK_HYPERVISOR_FREE");
        self.create_hook("HOOK_HYPERVISOR_MIGRATEDVM_LEAVE");
        self.create_hook("HOOK_HYPERVISOR_MIGRATEDVM_ARRIVE");
        self.create_hook("HOOK_HYPERVISOR_CLONE")
        
        # module inits;
        self.initialize_modules()
        
        
        # libvirt connection
        self.libvirt_connection = libvirt.open(self.local_libvirt_uri)
        if self.libvirt_connection == None:
            log.error("unable to connect libvirt")
            sys.exit(-42) 
        log.info("connected to  libvirt")
        self.libvirt_event_callback_id = self.libvirt_connection.domainEventRegisterAny(None, libvirt.VIR_DOMAIN_EVENT_ID_LIFECYCLE, self.hypervisor_on_domain_event, None) 
        
        self.capabilities = self.get_capabilities()
        
        # persistance
        self.manage_persistance()
        
        # action on auth
        self.register_actions_to_perform_on_auth("set_vcard")
        self.register_actions_to_perform_on_auth("update_presence")
        
    
    
    def update_presence(self, params=None):
        count   = len(self.virtualmachines)
        nup     = 0
        status  = ARCHIPEL_XMPP_SHOW_ONLINE + " (" + str(count) + ")"
        self.change_presence(self.xmppstatusshow, status)
    
    
    def register_handler(self):
        """
        this method overrides the defaut register_handler of the super class.
        """
        TNArchipelEntity.register_handler(self)
        
        self.xmppclient.RegisterHandler('iq', self.process_iq, ns=ARCHIPEL_NS_HYPERVISOR_CONTROL)
    
    def init_permissions(self):
        """initialize the permssions"""
        TNArchipelEntity.init_permissions(self)
        self.permission_center.create_permission("alloc", "Authorizes users to allocate new virtual machines", False);
        self.permission_center.create_permission("free", "Authorizes users to free allocated virtual machines", False);
        self.permission_center.create_permission("rostervm", "Authorizes users to access the hypervisor's roster", False);
        self.permission_center.create_permission("clone", "Authorizes users to clone virtual machines", False);
        self.permission_center.create_permission("ip", "Authorizes users to get hypervisor's IP address", False);
        self.permission_center.create_permission("uri", "Authorizes users to get the hypervisor's libvirt URI", False);
        self.permission_center.create_permission("capabilities", "Authorizes users to access the hypervisor capabilities", False);
    
    
    def manage_persistance(self):
        """
        if the database_file parameter contain a valid populated sqlite3 database,
        this method will recreate all the old L{TNArchipelVirtualMachine}. if not, it will create a 
        blank database file.
        """
        log.info("opening database file {0}".format(self.database_file))
        self.database = sqlite3.connect(self.database_file, check_same_thread=False)
        
        log.info("populating database if not exists")
        
        self.database.execute("create table if not exists virtualmachines (jid text, password text, creation_date date, comment text, name text)")
            
        c = self.database.cursor()
        c.execute("select * from virtualmachines")
        for vm in c:
            string_jid, password, date, comment, name = vm
            jid = xmpp.JID(string_jid)
            jid.setResource(self.jid.getNode())
            vm = self.create_threaded_vm(jid, password, name)
            self.virtualmachines[vm.jid.getNode()] = vm.get_instance()
    
        
    def create_threaded_vm(self, jid, password, name):
        """
        this method creates a threaded L{TNArchipelVirtualMachine}, start it and return the Thread instance
        @type jid: string
        @param jid: the JID of the L{TNArchipelVirtualMachine}
        @type password: string
        @param password: the password associated to the JID
        @rtype: L{TNThreadedVirtualMachine}
        @return: a L{TNThreadedVirtualMachine} instance of the virtual machine
        """
        vm = TNThreadedVirtualMachine(jid, password, self, self.configuration, name)
        #vm.daemon = True
        vm.start()
        return vm    
    
    
    def generate_name(self):
        return self.generated_names[random.randint(0, self.number_of_names)].replace("\n", "")
    
    
    
    
    ### LIBVIRT events Processing
    
    
    def hypervisor_on_domain_event(self, conn, dom, event, detail, opaque):
        """
        trigger when a domain trigger vbent. We care only about RESUMED and SHUTDOWNED from MIGRATED
        """
        if event == libvirt.VIR_DOMAIN_EVENT_STOPPED and detail == libvirt.VIR_DOMAIN_EVENT_STOPPED_MIGRATED:
            try:
                strdesc = dom.XMLDesc(0)
                desc    = xmpp.simplexml.NodeBuilder(data=strdesc).getDom()
                vmjid   = desc.getTag(name="description").getCDATA().split("::::")[0]
                log.info("MIGRATION: virtual machine %s stopped because of live migration. Freeing softly" % vmjid)
                self.free_for_migration(xmpp.JID(vmjid))
                self.perform_hooks("HOOK_HYPERVISOR_MIGRATEDVM_LEAVE", dom)
            except Exception as ex:
                log.error("MIGRATION: can't free softly this virtual machine: %s" % str(ex))
            
        elif event == libvirt.VIR_DOMAIN_EVENT_RESUMED and detail == libvirt.VIR_DOMAIN_EVENT_RESUMED_MIGRATED:
            try:
                strdesc = dom.XMLDesc(0)
                desc    = xmpp.simplexml.NodeBuilder(data=strdesc).getDom()
                vmjid   = desc.getTag(name="description").getCDATA().split("::::")[0]
                vmpass  = desc.getTag(name="description").getCDATA().split("::::")[1]
                vmname  = desc.getTag(name="description").getCDATA().split("::::")[2]
                log.info("MIGRATION: virtual machine %s resumed from live migration. Allocating softly" % vmjid)
                self.alloc_for_migration(xmpp.JID(vmjid), vmname, vmpass)
                self.perform_hooks("HOOK_HYPERVISOR_MIGRATEDVM_ARRIVE", dom)
            except Exception as ex:
                log.warning("MIGRATION: can't alloc softly this virtual machine. Maybe it is not an archipel VM: %s" % str(ex))
            
    
    
    
    
    
    ### XMPP Processing
    
    
    def process_iq(self, conn, iq):
        """
        this method is invoked when a ARCHIPEL_NS_HYPERVISOR_CONTROL IQ is received.
        
        it understands IQ of type:
            - alloc
            - free
            
        @type conn: xmpp.Dispatcher
        @param conn: ths instance of the current connection that send the stanza
        @type iq: xmpp.Protocol.Iq
        @param iq: the received IQ
        """
        action = self.check_acp(conn, iq)
        self.check_perm(conn, iq, action, -1)
        
        if action == "alloc":
            reply = self.iq_alloc(iq)
            conn.send(reply)
            raise xmpp.protocol.NodeProcessed
            
        elif action == "free":
            reply = self.iq_free(iq)
            conn.send(reply)
            raise xmpp.protocol.NodeProcessed
            
        elif action == "rostervm":
            reply = self.iq_roster(iq)
            conn.send(reply)
            raise xmpp.protocol.NodeProcessed
            
        elif action == "clone":
            reply = self.iq_clone(iq)
            conn.send(reply)
            raise xmpp.protocol.NodeProcessed
        
        elif action == "ip":
            reply = self.iq_ip(iq)
            conn.send(reply)
            raise xmpp.protocol.NodeProcessed
            
        elif action == "uri":
            reply = self.iq_libvirt_uri(iq)
            conn.send(reply)
            raise xmpp.protocol.NodeProcessed
            
        elif action == "capabilities":
            reply = self.iq_capabilities(iq)
            conn.send(reply)
            raise xmpp.protocol.NodeProcessed
        
    
    
    
    
    
    ###  Hypervisor controls
    
    
    def alloc(self, requester=None, requested_name=None):
        """
        Alloc a new XMPP entity
        """
        vmuuid      = str(uuid.uuid1())
        vm_password = ''.join([random.choice(string.letters + string.digits) for i in range(self.configuration.getint("VIRTUALMACHINE", "xmpp_password_size"))])
        vm_jid      = xmpp.JID(node=vmuuid.lower(), domain=self.xmppserveraddr.lower(), resource=self.jid.getNode().lower())
        
        log.info("adding the xmpp vm %s to my roster" % (str(vm_jid)))
        
        self.add_jid(vm_jid, [ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR])
        
        if not requested_name:
            name = self.generate_name()
        else:
            name = requested_name
        
        log.info("starting xmpp threaded virtual machine")
        vm = self.create_threaded_vm(vm_jid, vm_password, name).get_instance()
        
        if requester:
            log.info("adding the requesting controller %s to the VM's roster" % (str(requester)))
            vm.register_actions_to_perform_on_auth("add_jid", xmpp.JID(requester), persistant=False)
            vm.permission_center.grant_permission_to_user("all", requester.getStripped())
        
        log.info("registering the new VM in hypervisor's memory")
        self.database.execute("insert into virtualmachines values(?,?,?,?,?)", (str(vm_jid.getStripped()), vm_password, datetime.datetime.now(), '', name))
        self.database.commit()
        self.virtualmachines[vmuuid] = vm
        
        self.update_presence()
        log.info("XMPP Virtual Machine instance sucessfully initialized")
        self.perform_hooks("HOOK_HYPERVISOR_ALLOC", vm)
        return vm
        
    
    
    def alloc_for_migration(self, jid, name, password):
        """
        perform light allocation (no registration, no subscription)
        
        @type jid: xmpp.JID
        @param jid: the JID of the migrated VM to alloc
        @type name: string
        @param name: the name of the migrated VM to alloc
        @type password: string
        @param password: the password of the migrated VM to alloc
        """
        uuid    = jid.getNode()
        
        jid.setResource(self.jid.getNode())
        log.info("starting xmpp threaded virtual machine with incoming jid : %s" % jid)
        vm = self.create_threaded_vm(jid, password, name).get_instance()
        
        log.info("registering the new VM in hypervisor's memory")
        self.database.execute("insert into virtualmachines values(?,?,?,?,?)", (str(jid.getStripped()), password, datetime.datetime.now(), '', name))
        self.database.commit()
        self.virtualmachines[uuid] = vm
        
        self.update_presence()
        log.info("Migrated XMPP VM is ready")
        return vm
        
    
    
    
    def free(self, jid):
        uuid    = jid.getNode()
        vm      = self.virtualmachines[uuid]
        
        if vm.is_migrating:
            raise Exception("virtual machine is migrating. Can't free")
        
        if vm.domain and (vm.domain.info()[0] == 1 or vm.domain.info()[0] == 2 or vm.domain.info()[0] == 3):
            vm.domain.destroy()
        
        if vm.domain:
            vm.domain.undefine()
        
        log.info("launch %s's terminate method" % (str(jid)))
        vm.terminate();
        
        log.info("removing the xmpp vm %s from my roster" % (str(jid)))
        self.remove_jid(jid)
        
        vm.remove_folder()
        
        log.info("unregistering the VM from hypervisor's database")
        self.database.execute("delete from virtualmachines where jid='%s'" % jid.getStripped())
        self.database.commit()
        
        del self.virtualmachines[uuid]
        
        log.info("unregistering vm from jabber server")
        vm.inband_unregistration()
        self.perform_hooks("HOOK_HYPERVISOR_FREE", vm)
        self.update_presence()
    
    
    def free_for_migration(self, jid):
        """
        perform light free (no removing of account, no unsubscription)
        @type jid: xmpp.JID
        @param jid: the JID of the migrated VM to free
        """
        uuid    = jid.getNode()
        vm      = self.virtualmachines[uuid]
        
        vm.undefine_and_disconnect()
        
        log.info("unregistering the VM from hypervisor's database")
        self.database.execute("delete from virtualmachines where jid='%s'" % jid.getStripped())
        self.database.commit()
        del self.virtualmachines[uuid]
        self.remove_jid(jid)
        self.update_presence()
    
    
    
    def clone(self, uuid, requester):
        xmppvm      = self.virtualmachines[uuid]
        xmldesc     = xmppvm.definition;
        
        if not xmldesc:
            raise Exception('The mother vm has to be defined to be cloned')
        
        dominfo = xmppvm.domain.info();
        if not (dominfo[0] == libvirt.VIR_DOMAIN_SHUTOFF or dominfo[0] == libvirt.VIR_DOMAIN_SHUTDOWN):
            raise Exception('The mother vm has to be stopped to be cloned')
        
        name = "%s (clone)" % xmppvm.name;
        newvm = self.alloc(requester, requested_name=name);
        newvm.register_actions_to_perform_on_auth("clone", {"definition": xmldesc, "path": xmppvm.folder, "baseuuid": uuid}, persistant=False)
        self.perform_hooks("HOOK_HYPERVISOR_CLONE", xmppvm)
        
    
    
    def get_capabilities(self):
        """return hypervisor's capabilities"""
        capp = xmpp.simplexml.NodeBuilder(data=self.libvirt_connection.getCapabilities()).getDom()
        return capp;
    
    
    
    
    ###  Hypervisor IQs
    
    
    def iq_alloc(self, iq):
        """
        this method creates a threaded L{TNArchipelVirtualMachine} with UUID given 
        as paylood in IQ and register the hypervisor and the iq sender in 
        the VM's roster
        @type iq: xmpp.Protocol.Iq
        @param iq: the sender request IQ
        @rtype: xmpp.Protocol.Iq
        @return: a ready-to-send IQ containing the results
        """
        try:
            try:
                requested_name = iq.getTag("query").getTag("archipel").getAttr("name")
            except:
                requested_name = None
        
            vm = self.alloc(iq.getFrom(), requested_name=requested_name)
        
            reply   = iq.buildReply("result")
            payload = xmpp.Node("virtualmachine", attrs={"jid": str(vm.jid.getStripped())})
            reply.setQueryPayload([payload])
        
            self.push_change("hypervisor", "alloc", excludedgroups=[ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR]);
            self.shout("virtualmachine", "A new Archipel Virtual Machine has been created by %s with uuid %s" % (iq.getFrom(), vm.uuid), excludedgroups=[ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR])
        except libvirt.libvirtError as ex:
            reply = build_error_iq(self, ex, iq, ex.get_error_code(), ns=ARCHIPEL_NS_LIBVIRT_GENERIC_ERROR)
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_ALLOC)
            
        return reply
    
    
    def iq_alloc_for_migration(self, iq):
        """
        Perform light allocation for handler migrating vm
        """
        try:
            reply       = iq.buildReply("result")
            vmjid       = xmpp.JID(iq.getTag("query").getTag("archipel").getAttr("jid"))
            name        = iq.getTag("query").getTag("archipel").getAttr("name")
            password    = iq.getTag("query").getTag("archipel").getAttr("password")
            
            self.alloc_for_migration(vmjid, name, password);
            
            self.push_change("hypervisor", "migrate", excludedgroups=[ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR]);
            self.shout("virtualmachine", "The virtual machine %s has been migrated from hypervisor %s" % (vmjid, iq.getFrom()), excludedgroups=[ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR])
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_ALLOC_MIGRATION)
        return reply
    
    
    
    def iq_free(self, iq):
        """
        this method destroy a threaded L{TNArchipelVirtualMachine} with UUID given 
        as paylood in IQ and remove it from the hypervisor roster
        
        @type iq: xmpp.Protocol.Iq
        @param iq: the sender request IQ
        @rtype: xmpp.Protocol.Iq
        @return: a ready-to-send IQ containing the results
        """
        reply = iq.buildReply("result")
        
        try:
            vm_jid      = xmpp.JID(jid=iq.getTag("query").getTag("archipel").getAttr("jid"))
            domain_uuid = vm_jid.getNode()
            
            self.free(vm_jid)
            
            reply.setQueryPayload([xmpp.Node(tag="virtualmachine", attrs={"jid": vm_jid})])
            log.info("XMPP Virtual Machine instance sucessfully destroyed")
            self.push_change("hypervisor", "free", excludedgroups=[ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR]);
            self.shout("virtualmachine", "The Archipel Virtual Machine %s has been destroyed by %s" % (domain_uuid, iq.getFrom()), excludedgroups=[ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR])
        except libvirt.libvirtError as ex:
            reply = build_error_iq(self, ex, iq, ex.get_error_code(), ns=ARCHIPEL_NS_LIBVIRT_GENERIC_ERROR)
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_FREE)
        
        return reply
    
    
    def iq_free_for_migration(self, iq):
        """
        perform light free for virtual machine migration
        """
        try:
            reply = iq.buildReply("result")
            vmjid = xmpp.JID(iq.getTag("query").getTag("archipel").getAttr("jid"))
            self.free_for_migration(vmjid);
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_FREE_MIGRATION)
        return reply
    
    
    
    def iq_clone(self, iq):
        """
        alloc a virtual as a clone of another
        
        @type iq: xmpp.Protocol.Iq
        @param iq: the received IQ
        
        @rtype: xmpp.Protocol.Iq
        @return: a ready to send IQ containing the result of the action
        """
        try:
            reply       = iq.buildReply("result")
            vmjid       = xmpp.JID(jid=iq.getTag("query").getTag("archipel").getAttr("jid"))
            vmuuid      = vmjid.getNode();
            
            self.clone(vmuuid, iq.getFrom())
            
            self.push_change("hypervisor", "clone", excludedgroups=[ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR]);
            self.shout("virtualmachine", "The Archipel Virtual Machine %s has been cloned by %s" % (vmuuid, iq.getFrom()), excludedgroups=[ARCHIPEL_XMPP_GROUP_VM, ARCHIPEL_XMPP_GROUP_HYPERVISOR])
            
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_CLONE)
        return reply
    
    
    def iq_roster(self, iq):
        """
        send the hypervisor roster content
        
        @type iq: xmpp.Protocol.Iq
        @param iq: the sender request IQ
        @rtype: xmpp.Protocol.Iq
        @return: a ready-to-send IQ containing the results
        """
        try:
            reply = iq.buildReply("result")
            nodes = []
            for uuid, vm in self.virtualmachines.iteritems():#self.roster.getItems():
                n = xmpp.Node("item")
                n.addData(vm.jid.getStripped())
                nodes.append(n)
            reply.setQueryPayload(nodes)
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_ROSTER)
        return reply
    
        
    def iq_ip(self, iq):
        """
        send the hypervisor IP address
        
        @type iq: xmpp.Protocol.Iq
        @param iq: the sender request IQ
        @rtype: xmpp.Protocol.Iq
        @return: a ready-to-send IQ containing the results
        """
        try:
            reply = iq.buildReply("result")
            reply.getTag("query").addChild(name="ip", payload=self.ipaddr);
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_IP)
        return reply
    
    
    def iq_libvirt_uri(self, iq):
        """
        send the hypervisor IP address
        
        @type iq: xmpp.Protocol.Iq
        @param iq: the sender request IQ
        @rtype: xmpp.Protocol.Iq
        @return: a ready-to-send IQ containing the results
        """
        try:
            network_libvirt_uri = self.local_libvirt_uri.replace("///", "//%s/" % self.resource)
            reply = iq.buildReply("result")
            reply.getTag("query").addChild(name="uri", payload=network_libvirt_uri);
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_LIBVIRT_URI)
        return reply
    
    
    def iq_capabilities(self, iq):
        """
        send the hypervisor capabilities
        
        @type iq: xmpp.Protocol.Iq
        @param iq: the sender request IQ
        @rtype: xmpp.Protocol.Iq
        @return: a ready-to-send IQ containing the results
        """
        try:
            reply = iq.buildReply("result")
            reply.setQueryPayload(self.capabilities)
        except Exception as ex:
            reply = build_error_iq(self, ex, iq, ARCHIPEL_ERROR_CODE_HYPERVISOR_CAPABILITIES)
        return reply
    

    

    