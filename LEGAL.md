<!-- SPDX-License-Identifier: MPL-2.0 -->
# Legal position

This document sets out what this project does, what it does not do, and the basis on which it is published. It is a statement of position, not legal advice, and it is written for anyone who needs to assess the project quickly — including the manufacturer.

## What the project is for

The toolkit exists to make a device its owner has already bought work with software its owner has written, and to study how that device behaves in order to write that software. That is interoperability and observation.

In the European Union, Directive 2009/24/EC provides for this. Article 5(3) allows a person entitled to use a copy of a program to observe, study and test its functioning in order to determine the ideas and principles underlying it, while performing acts they are entitled to perform. Article 6 permits reproduction and translation of code where indispensable to obtain the information necessary to achieve interoperability of an independently created program. In French law the corresponding provisions are article L.122-6-1 IV of the Code de la propriété intellectuelle, for observation and study, and article L.122-6-1 III for acts necessary to use the program in accordance with its purpose.

The work here is confined to that purpose. It targets one device and one firmware revision, it is used on hardware the operator owns, and its output is of no use to anyone who does not have that hardware in front of them.

## What is not distributed

Nothing in this repository, its history, or its releases contains:

- any encryption key, or material from which one can be derived;
- any firmware image, update package, or filesystem image of the device;
- any binary authored by the manufacturer;
- any font, typeface, or other licensed resource belonging to a third party.

Where the toolkit needs material of that kind, the operator produces it on their own machine and points the toolkit at it. Locations are configured locally, in files that are never committed. The project does not fetch such material, does not tell anyone where to find it, and does not accept contributions that add either capability.

Where the device runs software covered by the GPL or LGPL, this project relies on the sources the manufacturer publishes itself in satisfaction of those licences, and on nothing else.

## The maintenance path

The mechanism the toolkit uses is the manufacturer's own maintenance path: the player, of its own accord, inspects inserted storage for a file it expects, and runs it if it decrypts.

That mechanism guards a service route into the device. It does not control access to any work, and it does not restrict any act of reproduction or communication of a protected work. A technical measure attracts protection under article L.331-5 CPI only where it is intended to prevent or limit uses not authorised by the holder of a copyright or neighbouring right *in a work*. Nothing here circumvents a measure of that kind, because there is no work behind this one to protect.

## The modification is not persistent

Nothing is written to the device's internal storage. The player copies its application into RAM at every start-up; the toolkit modifies that copy, in memory, on the owner's own device. Removing the storage medium and power-cycling the player returns it to its shipped state with no trace and no further action. No update is installed, no partition is written, and no manufacturer file is replaced.

## Warranty and risk

Modifying a device may void its warranty. The manufacturer is under no obligation to support a device that has been modified. Anyone using this project does so on their own equipment and at their own risk; the licence's disclaimer of warranty applies in full.

## Trade marks

Pioneer DJ, XDJ and rekordbox are trade marks of their respective owners. They are used here only to identify the hardware this project is compatible with, which is nominative use. This project is not affiliated with, endorsed by, or connected to those owners in any way.

## If you believe something here is wrong

Open an issue on this repository naming the file or passage concerned and the reason. If it should not be public, use GitHub's private report form on this repository, under Security, Report a vulnerability. A complaint will be acknowledged and looked at on its merits, and where it is well founded the material will be removed. That commitment is made independently of whether the objection arrives as a formal notice.

Security findings follow a different route, set out in [SECURITY.md](SECURITY.md).
