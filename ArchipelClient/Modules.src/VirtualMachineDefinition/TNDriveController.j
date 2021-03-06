/*
 * TNWindowDriveEdition.j
 *
 * Copyright (C) 2010 Antoine Mercadal <antoine.mercadal@inframonde.eu>
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as
 * published by the Free Software Foundation, either version 3 of the
 * License, or (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

@import "TNDriveObject.j"

TNArchipelTypeVirtualMachineDisk       = @"archipel:vm:disk";

TNArchipelTypeVirtualMachineDiskGet    = @"get";
TNArchipelTypeVirtualMachineISOGet     = @"getiso";

TNXMLDescDriveTypeFile      = @"file";
TNXMLDescDriveTypeBlock     = @"block";
TNXMLDescDriveTypes         = [TNXMLDescDriveTypeFile, TNXMLDescDriveTypeBlock];

TNXMLDescDiskTargetHda  = @"hda";
TNXMLDescDiskTargetHdb  = @"hdb";
TNXMLDescDiskTargetHdc  = @"hdc";
TNXMLDescDiskTargetHdd  = @"hdd";
TNXMLDescDiskTargetSda  = @"sda";
TNXMLDescDiskTargetSdb  = @"sdb";
TNXMLDescDiskTargetSdc  = @"sdc";
TNXMLDescDiskTargetSdd  = @"sdd";

TNXMLDescDiskTargets        = [ TNXMLDescDiskTargetHda, TNXMLDescDiskTargetHdb,
                                TNXMLDescDiskTargetHdc, TNXMLDescDiskTargetHdd,
                                TNXMLDescDiskTargetSda, TNXMLDescDiskTargetSdb,
                                TNXMLDescDiskTargetSdc, TNXMLDescDiskTargetSdd];
TNXMLDescDiskTargetsIDE     = [ TNXMLDescDiskTargetHda, TNXMLDescDiskTargetHdb,
                                TNXMLDescDiskTargetHdc, TNXMLDescDiskTargetHdd];
TNXMLDescDiskTargetsSCSI    = [ TNXMLDescDiskTargetSda, TNXMLDescDiskTargetSdb,
                                TNXMLDescDiskTargetSdc, TNXMLDescDiskTargetSdd]

TNXMLDescDiskBusIDE     = @"ide";
TNXMLDescDiskBusSCSI    = @"scsi";
TNXMLDescDiskBusVIRTIO  = @"virtio";
TNXMLDescDiskBuses      = [TNXMLDescDiskBusIDE, TNXMLDescDiskBusSCSI, TNXMLDescDiskBusVIRTIO];


/*! @ingroup virtualmachinedefinition
    this is the virtual drive editor
*/
@implementation TNDriveController : CPObject
{
    @outlet CPWindow        mainWindow;
    @outlet CPPopUpButton   buttonBus;
    @outlet CPPopUpButton   buttonSource;
    @outlet CPPopUpButton   buttonTarget;
    @outlet CPPopUpButton   buttonType;
    @outlet CPRadioGroup    radioDriveType;
    @outlet CPTextField     fieldDevicePath;

    id                      _delegate       @accessors(property=delegate);
    CPTableView             _table          @accessors(property=table);
    TNNetworkDrive          _drive          @accessors(property=drive);
    TNStropheContact        _entity         @accessors(property=entity);
}


#pragma mark -
#pragma mark Initialization

/*! called at cib awaking
*/
- (void)awakeFromCib
{
    [buttonType removeAllItems];
    [buttonTarget removeAllItems];
    [buttonBus removeAllItems];
    [buttonSource removeAllItems];

    [buttonType addItemsWithTitles:TNXMLDescDriveTypes];
    [buttonTarget addItemsWithTitles:TNXMLDescDiskTargetsIDE];
    [buttonBus addItemsWithTitles:TNXMLDescDiskBuses];
}


#pragma mark -
#pragma mark Utilities

/*! send this message to update GUI according to permissions
*/
- (void)updateAfterPermissionChanged
{
    for (var i = 0; i < [[radioDriveType radios] count]; i++)
    {
        var radio = [[radioDriveType radios] objectAtIndex:i];

        switch ([[radio title] lowercaseString])
        {
            case @"hard drive":
                    [_delegate setControl:radio enabledAccordingToPermission:@"drives_get"];
                    break;
            case @"cd/dvd":
                [_delegate setControl:radio enabledAccordingToPermission:@"drives_getiso"];
                    break;
        }
    }
}

/*! update the editor according to the current drive to edit
*/
- (void)update
{
    [radioDriveType setTarget:nil];
    for (var i = 0; i < [[radioDriveType radios] count]; i++)
    {
        var radio = [[radioDriveType radios] objectAtIndex:i];
        if ((([radio title] == @"Hard drive") && ([_drive device] == @"disk"))
            ||  (([radio title] == @"CD/DVD") && ([_drive device] == @"cdrom")) )
        {
            [radio setState:CPOnState];
            break;
        }
    }
    [radioDriveType setTarget:self];

    [self updateAfterPermissionChanged];

    if (([_drive device] == @"disk") && [_delegate currentEntityHasPermission:@"drives_get"])
        [self getDisksInfo];
    else if (([_drive device] == @"cdrom")  && [_delegate currentEntityHasPermission:@"drives_getiso"])
        [self getISOsInfo];


    [buttonType selectItemWithTitle:[_drive type]];

    [buttonType selectItemWithTitle:[_drive type]]
    [self driveTypeDidChange:nil];

    [buttonTarget selectItemWithTitle:[_drive target]];
    [buttonBus selectItemWithTitle:[_drive bus]];

    [buttonBus setTarget:self];
    [buttonBus setAction:@selector(populateTargetButton:)];

    [self populateTargetButton:nil];
}


#pragma mark -
#pragma mark Actions

/*! saves the change
    @param aSender the sender of the action
*/
- (IBAction)save:(id)aSender
{
    if ([buttonSource isEnabled] && [buttonSource selectedItem])
    {
        [_drive setSource:[[buttonSource selectedItem] stringValue]];
    }
    else if ([buttonType title] == TNXMLDescDriveTypeBlock)
    {
        [_drive setSource:[fieldDevicePath stringValue]];
    }
    else if ([buttonType title] == TNXMLDescDriveTypeFile)
    {
        [_drive setSource:([_drive device] == @"cdrom") ? @"" : @"/tmp/nodisk"];
    }

    [_drive setType:[buttonType title]];

    var driveType = [[radioDriveType selectedRadio] title];

    if (driveType == @"Hard drive")
        [_drive setDevice:@"disk"];
    else
        [_drive setDevice:@"cdrom"];


    [_drive setTarget:[buttonTarget title]];
    [_drive setBus:[buttonBus title]];

    [_table reloadData];

    [_delegate defineXML:aSender];
    [mainWindow close];
}

/*! populate the target button
    @param aSender the sender of the action
*/
- (IBAction)populateTargetButton:(id)aSender
{
    [buttonTarget removeAllItems];

    switch ([buttonBus title])
    {
        case TNXMLDescDiskBusIDE:
            [buttonTarget addItemsWithTitles:TNXMLDescDiskTargetsIDE];
            break;

        case TNXMLDescDiskBusSCSI:
            [buttonTarget addItemsWithTitles:TNXMLDescDiskTargetsSCSI];
            break;

        case TNXMLDescDiskBusVIRTIO:
            [buttonTarget addItemsWithTitles:TNXMLDescDiskTargets];
            break;
    }

    [buttonTarget selectItemWithTitle:[_drive target]];
}

/*! change the type of the drive
    @param aSender the sender of the action
*/
- (IBAction)performRadioDriveTypeChanged:(id)aSender
{
    var driveType = [[radioDriveType selectedRadio] title];

    if (driveType == @"Hard drive")
    {
        switch ([buttonBus title])
        {
            case TNXMLDescDiskBusIDE:
                [buttonTarget selectItemWithTitle:@"hda"]
                break;

            case TNXMLDescDiskBusSCSI:
                [buttonTarget selectItemWithTitle:@"sda"];
                break;

            case TNXMLDescDiskBusVIRTIO:
                [buttonTarget selectItemWithTitle:@"hda"];
                break;
        }

        [self getDisksInfo];
    }
    else
    {
        switch ([buttonBus title])
        {
            case TNXMLDescDiskBusIDE:
                [buttonTarget selectItemWithTitle:@"hdc"]
                break;

            case TNXMLDescDiskBusSCSI:
                [buttonTarget selectItemWithTitle:@"sdc"];
                break;

            case TNXMLDescDiskBusVIRTIO:
                [buttonTarget selectItemWithTitle:@"hdc"];
                break;
        }

        [self getISOsInfo];
    }
}

/*! hange the type of the drive (file or block)
    @param aSender the sender of the action
*/
- (IBAction)driveTypeDidChange:(id)aSender
{
    if ([buttonType title] == TNXMLDescDriveTypeBlock)
    {
        [fieldDevicePath setHidden:NO];
        [buttonSource setHidden:YES];

        [fieldDevicePath setEnabled:YES];
        [buttonSource setEnabled:NO];

        if (aSender)
            [fieldDevicePath setStringValue:@"/dev/cdrom"];
        else
            [fieldDevicePath setStringValue:[_drive source]];
    }
    else if ([buttonType title] == TNXMLDescDriveTypeFile)
    {
        [fieldDevicePath setHidden:YES];
        [buttonSource setHidden:NO];

        [fieldDevicePath setEnabled:NO];
        [buttonSource setEnabled:YES];

        [fieldDevicePath setStringValue:@""];
    }
}

/*! show the main window
    @param aSender the sender of the action
*/
- (IBAction)showWindow:(id)aSender
{
    [mainWindow center];
    [mainWindow makeKeyAndOrderFront:aSender];

    [self update];
}

/*! hide the main window
    @param aSender the sender of the action
*/
- (IBAction)hideWindow:(id)aSender
{
    [mainWindow close];
}



#pragma mark -
#pragma mark  XMPP Controls

/*! ask virtual machine for its drives
*/
- (void)getDisksInfo
{
    var stanza = [TNStropheStanza iqWithType:@"get"];

    [stanza addChildWithName:@"query" andAttributes:{"xmlns": TNArchipelTypeVirtualMachineDisk}];
    [stanza addChildWithName:@"archipel" andAttributes:{
        "action": TNArchipelTypeVirtualMachineDiskGet}];

    [_entity sendStanza:stanza andRegisterSelector:@selector(_didReceiveDisksInfo:) ofObject:self];
}

/*! compute virtual machine drives
    @param aStanza TNStropheStanza containing the answer
*/
- (BOOL)_didReceiveDisksInfo:(TNStropheStanza)aStanza
{
    if ([aStanza type] == @"result")
    {
        var disks = [aStanza childrenWithName:@"disk"];
        [buttonSource removeAllItems];

        for (var i = 0; i < [disks count]; i++)
        {
            var disk    = [disks objectAtIndex:i],
                vSize   = [[[disk valueForAttribute:@"virtualSize"] componentsSeparatedByString:@" "] objectAtIndex:0],
                label   = [[[disk valueForAttribute:@"name"] componentsSeparatedByString:@"."] objectAtIndex:0] + " - " + vSize  + " (" + [disk valueForAttribute:@"diskSize"] + ")",
                item    = [[TNMenuItem alloc] initWithTitle:label action:nil keyEquivalent:nil];

            [item setStringValue:[disk valueForAttribute:@"path"]];
            [buttonSource addItem:item];
        }

        for (var i = 0; i < [[buttonSource itemArray] count]; i++)
        {
            var item  = [[buttonSource itemArray] objectAtIndex:i];

            if ([item stringValue] == [_drive source])
            {
                [buttonSource selectItem:item];
                break;
            }
        }
    }

    return NO;
}

/*! ask virtual machine for avaiable ISOs
*/
- (void)getISOsInfo
{
    var stanza = [TNStropheStanza iqWithType:@"get"];

    [stanza addChildWithName:@"query" andAttributes:{"xmlns": TNArchipelTypeVirtualMachineDisk}];
    [stanza addChildWithName:@"archipel" andAttributes:{"action": TNArchipelTypeVirtualMachineISOGet}];

    [_entity sendStanza:stanza andRegisterSelector:@selector(didReceiveISOsInfo:) ofObject:self];
}

/*! compute virtual machine ISOs
    @param aStanza TNStropheStanza containing the answer
*/
- (BOOL)didReceiveISOsInfo:(TNStropheStanza)aStanza
{
    if ([aStanza type] == @"result")
    {
        var isos = [aStanza childrenWithName:@"iso"];

        [buttonSource removeAllItems];

        for (var i = 0; i < [isos count]; i++)
        {
            var iso     = [isos objectAtIndex:i],
                label   = [iso valueForAttribute:@"name"],
                item    = [[TNMenuItem alloc] initWithTitle:label action:nil keyEquivalent:nil];

            [item setStringValue:[iso valueForAttribute:@"path"]];
            [buttonSource addItem:item];
        }

        for (var i = 0; i < [[buttonSource itemArray] count]; i++)
        {
            var item  = [[buttonSource itemArray] objectAtIndex:i];

            if ([item stringValue] == [_drive source])
            {
                [buttonSource selectItem:item];
                break;
            }
        }
    }

    return NO;
}

@end
