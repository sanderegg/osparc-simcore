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

qx.Class.define("osparc.notification.NotificationUI", {
  extend: qx.ui.core.Widget,

  construct: function(notification) {
    this.base(arguments);

    this.set({
      margin: 4,
      maxWidth: this.self().MAX_WIDTH,
      padding: this.self().PADDING,
      cursor: "pointer"
    });

    const layout = new qx.ui.layout.Grid(10, 3);
    layout.setColumnAlign(0, "center", "middle");
    layout.setColumnAlign(1, "left", "middle");
    layout.setColumnFlex(1, 1);
    this._setLayout(layout);

    if (notification) {
      this.setNotification(notification);
    }

    this.addListener("tap", () => this.__notificationTapped());
  },

  events: {
    "notificationTapped": "qx.event.type.Event"
  },

  properties: {
    notification: {
      check: "osparc.notification.Notification",
      init: null,
      nullable: false,
      apply: "__applyNotification"
    }
  },

  statics: {
    MAX_WIDTH: 300,
    PADDING: 10
  },

  members: {
    _createChildControlImpl: function(id) {
      let control;
      switch (id) {
        case "icon":
          control = new qx.ui.basic.Image().set({
            source: "@FontAwesome5Solid/paw/14",
            alignX: "center",
            alignY: "middle",
            minWidth: 18
          });
          this._add(control, {
            row: 0,
            column: 0,
            rowSpan: 3
          });
          break;
        case "title":
          control = new qx.ui.basic.Label().set({
            font: "text-13",
            rich: true,
            wrap: true
          });
          this._add(control, {
            row: 0,
            column: 1
          });
          break;
        case "text":
          control = new qx.ui.basic.Label().set({
            font: "text-12",
            rich: true,
            wrap: true
          });
          this._add(control, {
            row: 1,
            column: 1
          });
          break;
        case "date":
          control = new qx.ui.basic.Label().set({
            font: "text-11",
            rich: true,
            wrap: true
          });
          this._add(control, {
            row: 2,
            column: 1
          });
          break;
      }
      return control || this.base(arguments, id);
    },

    __applyNotification: function(notification) {
      const icon = this.getChildControl("icon");
      switch (notification.getCategory()) {
        case "NEW_ORGANIZATION":
          icon.setSource("@FontAwesome5Solid/users/14");
          break;
        case "STUDY_SHARED":
          icon.setSource("@FontAwesome5Solid/file/14");
          break;
        case "TEMPLATE_SHARED":
          icon.setSource("@FontAwesome5Solid/copy/14");
          break;
        case "CONVERSATION_NOTIFICATION":
          icon.setSource("@FontAwesome5Solid/bell/14");
          break;
        case "ANNOTATION_NOTE":
          icon.setSource("@FontAwesome5Solid/file/14");
          break;
        case "WALLET_SHARED":
          icon.setSource("@MaterialIcons/account_balance_wallet/14");
          break;
      }

      const titleLabel = this.getChildControl("title");
      titleLabel.setValue(notification.getTitle());

      const descriptionLabel = this.getChildControl("text");
      descriptionLabel.setValue(notification.getText());

      const date = this.getChildControl("date");
      notification.bind("date", date, "value", {
        converter: value => {
          if (value) {
            return osparc.utils.Utils.formatDateAndTime(new Date(value));
          }
          return "";
        }
      });

      const highlight = mouseOn => {
        this.set({
          backgroundColor: mouseOn ? "strong-main" : "transparent"
        })
      };
      this.addListener("mouseover", () => highlight(true));
      this.addListener("mouseout", () => highlight(false));
      highlight(false);

      // this will trigger calls to the backend, so only make them if necessary
      this.addListenerOnce("appear", () => this.__enrichTexts());
    },

    __enrichTexts: function() {
      const notification = this.getNotification();

      let resourceId = null;
      if (notification.getResourceId()) {
        resourceId = notification.getResourceId();
      } else if (notification.getActionablePath()) {
        // extract it from the actionable path
        const actionablePath = notification.getActionablePath();
        resourceId = actionablePath.split("/")[1];
      }

      const userFromId = notification.getUserFromId();
      const titleLabel = this.getChildControl("title");
      const descriptionLabel = this.getChildControl("text");

      switch (notification.getCategory()) {
        case "NEW_ORGANIZATION":
          if (resourceId) {
            const org = osparc.store.Groups.getInstance().getOrganization(resourceId);
            if (org) {
              descriptionLabel.setValue("You're now member of '" + org.getLabel() + "'");
            } else {
              this.setEnabled(false);
            }
          }
          break;
        case "STUDY_SHARED":
          if (resourceId) {
            osparc.store.Study.getInstance().getOne(resourceId)
              .then(study => {
                const studyAlias = osparc.product.Utils.getStudyAlias({
                  firstUpperCase: true
                });
                titleLabel.setValue(`${studyAlias} '${study["name"]}'`);
              })
              .catch(() => this.setEnabled(false));
          }
          if (userFromId) {
            const user = osparc.store.Groups.getInstance().getUserByUserId(userFromId);
            if (user) {
              descriptionLabel.setValue("was shared by " + user.getLabel());
            }
          }
          break;
        case "TEMPLATE_SHARED":
          if (resourceId) {
            osparc.store.Templates.fetchTemplate(resourceId)
              .then(templateData => {
                if (templateData) {
                  titleLabel.setValue(templateData["name"]);
                }
              })
              .catch(() => this.setEnabled(false));
          }
          if (userFromId) {
            const user = osparc.store.Groups.getInstance().getUserByUserId(userFromId);
            if (user) {
              descriptionLabel.setValue("was shared by " + user.getLabel());
            }
          }
          break;
        case "CONVERSATION_NOTIFICATION":
          if (resourceId) {
            osparc.store.Study.getInstance().getOne(resourceId)
              .then(study => titleLabel.setValue(`You were notified in '${study["name"]}'`))
              .catch(() => this.setEnabled(false));
          }
          if (userFromId) {
            const user = osparc.store.Groups.getInstance().getUserByUserId(userFromId);
            if (user) {
              descriptionLabel.setValue(user.getLabel() + " wants you to check the conversation");
            }
          }
          break;
        case "ANNOTATION_NOTE":
          if (resourceId) {
            osparc.store.Study.getInstance().getOne(resourceId)
              .then(study => titleLabel.setValue(`Note added in '${study["name"]}'`))
              .catch(() => this.setEnabled(false));
          }
          if (userFromId) {
            const user = osparc.store.Groups.getInstance().getUserByUserId(userFromId);
            if (user) {
              descriptionLabel.setValue("was added by " + user.getLabel());
            }
          }
          break;
        case "WALLET_SHARED":
          break;
      }
    },

    __notificationTapped: function() {
      const notification = this.getNotification();
      if (!notification) {
        return;
      }

      this.fireEvent("notificationTapped");
      osparc.notification.Notifications.markAsRead(notification);
      this.__openActionablePath(notification);
    },

    __openActionablePath: function(notification) {
      const actionablePath = notification.getActionablePath();
      const items = actionablePath.split("/");
      const resourceId = items.pop();
      const category = notification.getCategory();
      switch (category) {
        case "NEW_ORGANIZATION":
          this.__openOrganizationDetails(parseInt(resourceId));
          break;
        case "TEMPLATE_SHARED":
        case "STUDY_SHARED":
        case "CONVERSATION_NOTIFICATION":
        case "ANNOTATION_NOTE":
          this.__openStudyDetails(resourceId, notification);
          break;
        case "WALLET_SHARED": {
          const walletsEnabled = osparc.desktop.credits.Utils.areWalletsEnabled();
          if (walletsEnabled) {
            this.__openWalletDetails(parseInt(resourceId));
          }
          break;
        }
      }
    },

    __openOrganizationDetails: function(orgId) {
      // make sure org is available
      const org = osparc.store.Groups.getInstance().getOrganization(orgId)
      if (org) {
        const orgsWindow = osparc.desktop.organizations.OrganizationsWindow.openWindow();
        orgsWindow.openOrganizationDetails(orgId);
      } else {
        const msg = this.tr("You don't have access anymore");
        osparc.FlashMessenger.logAs(msg, "WARNING");
      }
    },

    __openStudyDetails: function(studyId, notification) {
      osparc.store.Study.getInstance().getOne(studyId)
        .then(studyData => {
          if (studyData) {
            const studyDataCopy = osparc.data.model.Study.deepCloneStudyObject(studyData);
            studyDataCopy["resourceType"] = notification.getCategory() === "TEMPLATE_SHARED" ? "template" : "study";
            const {
              resourceDetails,
              window,
            } = osparc.dashboard.ResourceDetails.popUpInWindow(studyDataCopy);

            resourceDetails.addListener("openStudy", () => {
              if (notification.getCategory() === "STUDY_SHARED") {
                const openCB = () => window.close();
                osparc.dashboard.ResourceBrowserBase.startStudyById(studyId, openCB);
              }
            });
            if (notification.getCategory() === "CONVERSATION_NOTIFICATION") {
              resourceDetails.addListener("pagesAdded", () => resourceDetails.openConversations());
            }
          }
        })
        .catch(err => {
          console.warn(err);
          const msg = this.tr("You don't have access anymore");
          osparc.FlashMessenger.logAs(msg, "WARNING");
        });
    },

    __openWalletDetails: function(walletId) {
      const wallet = osparc.desktop.credits.Utils.getWallet(walletId);
      if (wallet) {
        const myAccountWindow = osparc.desktop.credits.BillingCenterWindow.openWindow();
        if (myAccountWindow.openWallets()) {
          const msg = this.tr("Do you want to make it the default Credit Account?");
          const win = new osparc.ui.window.Confirmation(msg).set({
            caption: this.tr("Default Credit Account"),
            confirmAction: "create"
          });
          win.center();
          win.open();
          win.addListener("close", () => {
            if (win.getConfirmed()) {
              const preferenceSettings = osparc.Preferences.getInstance();
              preferenceSettings.requestChangePreferredWalletId(walletId);
            }
          }, this);
        }
      } else {
        const msg = this.tr("You don't have access anymore");
        osparc.FlashMessenger.logAs(msg, "WARNING");
      }
    }
  }
});
