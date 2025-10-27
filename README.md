# Blend Sanitizer

#### A Blender Addon for removing sensitive info from up your `.blend` files

> Made for _**Blender 4.2.7**_

<br/>

> [!WARNING!]
> This project is sill vary much a in a _"barely"_ working state! If you have any issues, please feel free to check the [issue tracker](https://github.com/errorbot1122/blender-sanitizer/issue)!

---

If you didn't know, `.blender` files by default store **absolute paths** to _all external files used in the project_.

This may seem like a non-issue at first, but these _paths_ give hints to _bad actors_ about **folder structure** and **folder names** leading towards each _external file_, eg. _your **Account Username** (Most likely your **real name**)_.

To prevent this its usually _good practice_ to click `File > External Data > Make Paths Relative` before _**exporting/sharing** your project..._ however, this can sill be an issue, as if the external file is far away the `.blend` file it can still expose any _intermediate folder names_, leaking **secrets**.

![L bozo can see HAHAHAHHAHA :rofl:... :|](https://i.imgur.com/da9jIF6.png)

The best way to be prevent exposing is to remember to move all external files _(even packed ones)_ into a folder directly under the `.blend` file. **And thats what this addon dose!**

All you have to do is whenever your ready to share your `.blend` file, go to `File > External Data > Sanitize File` and **_voilà_**, all your external files are copied into your an `assets` folder right beside your `.blend` file.

![Kind like this... :O](https://i.imgur.com/B4fc78C.png)

_Don't like the name `assets`?_ you can change it to whatever and wherever you want in the **Addon's Preferences menu**! _(`//` is substituted for the location of you `.blend` file)_

![Preferences > Add-ons > Blend Sanitizer > Copy Path = "//assets"](https://i.imgur.com/f4zVVBP.png)

_Want more control over where each Datablock goes?_ Open the _Manage popup_ at `File > External Data > Manage Sanitize-able Data` and handle each file separately!

![Gif of user using Manage Sanitize-able Data popup](https://i.imgur.com/jFdniFO.gif)

---

## Installing

_Wanna use the **"microtool"** yourself?_ Well here is how you **Installing it!**

1.  _Download_ the **latest release** _<small><small>(top)</small></small>_ **zip [here](ADD RELEASE ZIP)**! <big>_**[!DO NOT EXTRACT!]**_</big>
2.  _Launch_ **Blender 4.2**.
3.  _Open_ `Preferences > Add-ons` then _hit_ the **small triangle button** on the _top-right_.
4.  _Hit_ the `Install from Disk` _option_ and _select_ the **release zip**
5.  Make sure the _add-on_ is **enabled** and _not grayed out_ in the list of all your _installed add-ons_ <small>_(current menu)_</small>
    _(If you can find it search `Blend Sanitizer` in the search on the top)_

---

## Building

Most people already know this, _but if you don't..._ **<small><small>(:eyes: Look out for _STEP 2_)</small></small>** here are the steps of how to build this project:

1.  Download the [source](github.com/Errorbot1122/blend-sanitizer).
    ```sh
    git clone github.com/Errorbot1122/blend-sanitizer.git
    cd blend-sanitizer
    ```
2.  Install `requirements` in a **local directory**.
    _<sub><sub>(So **Blender** can recognize external packages)</sub></sub>_
    ```sh
    mkdir site-packages
    pip3 install --target ./site-packages/ -r requirements.txt
    ```
3.  Create a [virtual environment](https://docs.python.org/3/library/venv.html) for _development_.
    ```sh
    python3 -m venv .venv
    source .venv/bin/activate # On Windows: source .venv/Scripts/activate
    ```
4.  Install `dev-requirements` in the _virtual environment_
    ```sh
    pip3 install -r dev-requirements.txt
    ```
