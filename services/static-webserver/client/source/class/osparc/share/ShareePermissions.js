/*
 * oSPARC - The SIMCORE frontend - https://osparc.io
 * Copyright: 2023 IT'IS Foundation - https://itis.swiss
 * License: MIT - https://opensource.org/licenses/MIT
 * Authors: Odei Maiz (odeimaiz)
 */

/**
 * Data structure for showing sharee permissions. Array of objects with the following keys
 * - accessible: boolean
 * - gid: string // sharee group id
 * - inaccessible_services: Array of objects with keys "key" and "version"
 */
qx.Class.define("osparc.share.ShareePermissions", {
  extend: qx.ui.core.Widget,

  construct: function(shareesData) {
    this.base(arguments);

    this._setLayout(new qx.ui.layout.VBox(25));

    this.__populateLayout(shareesData);
  },

  statics: {
    checkShareePermissions: function(studyId, gids) {
      const promises = [];
      gids.forEach(gid => {
        const params = {
          url: {
            studyId,
            gid,
          }
        };
        promises.push(osparc.data.Resources.fetch("studies", "checkShareePermissions", params));
      });
      Promise.all(promises)
        .then(shareesData => {
          const inaccessibleShareesData = shareesData.filter(value => value["accessible"] === false);
          if (inaccessibleShareesData.length) {
            const shareePermissions = new osparc.share.ShareePermissions(inaccessibleShareesData);
            const caption = qx.locale.Manager.tr("Sharee permissions");
            const win = osparc.ui.window.Window.popUpInWindow(shareePermissions, caption, 500, 500, "@FontAwesome5Solid/exclamation-triangle/14").set({
              clickAwayClose: false,
              resizable: true,
              showClose: true
            });
            win.getChildControl("icon").set({
              textColor: "warning-yellow"
            });
          }
        });
    },
  },

  members: {
    __populateLayout: function(shareesData) {
      const text = this.tr("The following users/groups will not be able to open the shared study, because they don't have access to some services. Please contact the service owner(s) to give permission.");
      this._add(new qx.ui.basic.Label().set({
        value: text,
        font: "text-14",
        rich: true,
        wrap: true
      }));

      const grid = new qx.ui.layout.Grid(20, 10);
      grid.setColumnAlign(0, "center", "middle");
      grid.setColumnAlign(1, "center", "middle");
      const layout = new qx.ui.container.Composite(grid);
      this._add(layout);
      for (let i=0; i<shareesData.length; i++) {
        const shareeData = shareesData[i];
        const group = osparc.store.Groups.getInstance().getGroup(shareeData["gid"]);
        if (group) {
          layout.add(new qx.ui.basic.Label(group.getLabel()), {
            row: i,
            column: 0
          });

          const vBox = new qx.ui.container.Composite(new qx.ui.layout.VBox(8));
          shareeData["inaccessible_services"].forEach(inaccessibleService => {
            const hBox = new qx.ui.container.Composite(new qx.ui.layout.HBox(5)).set({
              alignY: "middle"
            });
            const infoButton = new qx.ui.form.Button(null, "@MaterialIcons/info_outline/14");
            infoButton.setAppearance("strong-button");
            const label = new qx.ui.basic.Label().set({
              alignY: "middle",
            });
            hBox.add(infoButton);
            hBox.add(label);
            osparc.store.Services.getService(inaccessibleService.key, inaccessibleService.version)
              .then(serviceMetadata => {
                label.setValue(serviceMetadata["name"] + " : " + serviceMetadata["version"])
                infoButton.addListener("execute", () => {
                  serviceMetadata["resourceType"] = "service";
                  osparc.dashboard.ResourceDetails.popUpInWindow(serviceMetadata);
                }, this);
              })

            vBox.add(hBox);
          });
          layout.add(vBox, {
            row: i,
            column: 1
          });
        }
      }
    }
  }
});
