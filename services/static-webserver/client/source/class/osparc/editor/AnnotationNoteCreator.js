/* ************************************************************************

   osparc - the simcore frontend

   https://osparc.io

   Copyright:
     2023 IT'IS Foundation, https://itis.swiss

   License:
     MIT: https://opensource.org/licenses/MIT

   Authors:
     * Odei Maiz (odeimaiz)

************************************************************************ */

qx.Class.define("osparc.editor.AnnotationNoteCreator", {
  extend: qx.ui.core.Widget,

  construct: function(study) {
    this.base(arguments);

    this.__study = study;

    this._setLayout(new qx.ui.layout.VBox(10));

    this.getChildControl("instructions");
    this.getChildControl("select-recipient");
    this.getChildControl("note");
    this.getChildControl("add");
  },

  properties: {
    recipientGid: {
      check: "Integer",
      init: null,
      nullable: true,
      event: "changeRecipientGid"
    },

    note: {
      check: "String",
      init: "",
      nullable: false,
      event: "changeNote"
    }
  },

  events: {
    "addNote": "qx.event.type.Event",
    "cancel": "qx.event.type.Event"
  },

  statics: {
    popUpInWindow: function(noteEditor) {
      const title = qx.locale.Manager.tr("Add Note");
      const win = osparc.ui.window.Window.popUpInWindow(noteEditor, title, 325, 256);
      win.center();
      win.open();
      return win;
    }
  },

  members: {
    _createChildControlImpl: function(id) {
      let control;
      switch (id) {
        case "instructions":
          control = new qx.ui.basic.Label().set({
            value: this.tr("Add a recipient to be notified. Please make sure the user has access to the ") + osparc.product.Utils.getStudyAlias() + ".",
            font: "text-14",
            rich: true,
            wrap: true
          });
          this._add(control);
          break;
        case "recipient-layout":
          control = new qx.ui.container.Composite(new qx.ui.layout.HBox(10)).set({
            alignY: "middle"
          });
          this._add(control);
          break;
        case "select-recipient":
          control = new qx.ui.form.Button(this.tr("Select recipient")).set({
            allowGrowX: false
          });
          control.addListener("execute", () => this.__selectRecipientTapped(), this);
          this.getChildControl("recipient-layout").add(control);
          break;
        case "selected-recipient":
          control = new qx.ui.basic.Label().set({
            font: "text-14",
            alignY: "middle"
          });
          this.getChildControl("recipient-layout").add(control, {
            flex: 1
          });
          break;
        case "note":
          control = new qx.ui.form.TextArea().set({
            font: "text-14",
            placeholder: this.tr("Note"),
            autoSize: true,
            minHeight: 70,
            maxHeight: 140
          });
          this.bind("note", control, "value");
          control.bind("value", this, "note");
          this._add(control);
          break;
        case "buttonsLayout": {
          control = new qx.ui.container.Composite(new qx.ui.layout.HBox(8).set({
            alignX: "right"
          }));
          const cancelButton = new qx.ui.form.Button(this.tr("Cancel"));
          cancelButton.addListener("execute", () => this.fireEvent("cancel"), this);
          control.add(cancelButton);
          this._add(control);
          break;
        }
        case "add": {
          const buttons = this.getChildControl("buttonsLayout");
          control = new qx.ui.form.Button(this.tr("Add"));
          control.addListener("execute", () => this.fireEvent("addNote"), this);
          buttons.addAt(control, 0);
          break;
        }
      }

      return control || this.base(arguments, id);
    },

    __selectRecipientTapped: function() {
      const currentStudyData = osparc.store.Store.getInstance().getCurrentStudy().serialize();
      currentStudyData["resourceType"] = "study";
      const usersManager = new osparc.share.NewCollaboratorsManager(currentStudyData, false, false).set({
        acceptOnlyOne: true,
      });
      usersManager.setCaption("Recipient");
      usersManager.getActionButton().setLabel(this.tr("Add"));
      usersManager.addListener("addCollaborators", e => {
        usersManager.close();
        const data = e.getData();
        const userGids = data["selectedGids"];
        if (userGids && userGids.length) {
          const userGid = parseInt(userGids[0]);
          this.__recipientSelected(userGid);
        }
      }, this);
    },

    __recipientSelected: function(userGid) {
      const currentAccessRights = this.__study.getAccessRights();
      if (userGid in currentAccessRights) {
        this.__setRecipientGid(userGid);
      } else {
        const msg = this.tr("This user has no access to the project. Do you want to share it?");
        const win = new osparc.ui.window.Confirmation(msg).set({
          caption: this.tr("Share"),
          confirmText: this.tr("Share"),
          confirmAction: "create"
        });
        win.center();
        win.open();
        win.addListener("close", () => {
          if (win.getConfirmed()) {
            const newCollaborators = {
              [userGid]: osparc.data.Roles.STUDY["write"].accessRights
            };
            const currentStudyData = osparc.store.Store.getInstance().getCurrentStudy().serialize();
            osparc.store.Study.getInstance().addCollaborators(currentStudyData, newCollaborators)
              .then(() => {
                this.__setRecipientGid(userGid);
                const potentialCollaborators = osparc.store.Groups.getInstance().getPotentialCollaborators()
                if (userGid in potentialCollaborators && "getUserId" in potentialCollaborators[userGid]) {
                  const uid = potentialCollaborators[userGid].getUserId();
                  osparc.notification.Notifications.pushStudyShared(uid, currentStudyData["uuid"]);
                }
              })
              .finally(() => collaboratorsManager.close());
          }
        });
      }
    },

    __setRecipientGid: function(gid) {
      this.setRecipientGid(gid);
      // only users were proposed
      const user = osparc.store.Groups.getInstance().getUserByGroupId(gid);
      if (user) {
        this.getChildControl("selected-recipient").setValue(user.getLabel());
      }
    }
  }
});
